"""
UserFriendlyTime by Rapptz
Source:
https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/time.py
"""
import re
from datetime import datetime

from discord.ext.commands import BadArgument, Converter

import parsedatetime as pdt
from dateutil.relativedelta import relativedelta

from core.models import getLogger

logger = getLogger(__name__)


class ShortTime:
    compiled = re.compile(
        r"""
                   (?:(?P<years>[0-9])(?:years?|y))?             # e.g. 2y
                   (?:(?P<months>[0-9]{1,2})(?:months?|mo))?     # e.g. 9mo
                   (?:(?P<weeks>[0-9]{1,4})(?:weeks?|w))?        # e.g. 10w
                   (?:(?P<days>[0-9]{1,5})(?:days?|d))?          # e.g. 14d
                   (?:(?P<hours>[0-9]{1,5})(?:hours?|h))?        # e.g. 12h
                   (?:(?P<minutes>[0-9]{1,5})(?:min(?:ute)?s?|m))?  # e.g. 10m
                   (?:(?P<seconds>[0-9]{1,5})(?:sec(?:ond)?s?|s))?  # e.g. 15s
                          """,
        re.VERBOSE,
    )

    def __init__(self, argument):
        match = self.compiled.fullmatch(argument)
        if match is None or not match.group(0):
            raise BadArgument("Invalid time provided.")

        data = {k: int(v) for k, v in match.groupdict(default="0").items()}
        now = datetime.utcnow()
        self.dt = now + relativedelta(**data)


# Monkey patch mins and secs into the units
units = pdt.pdtLocales["en_US"].units
units["minutes"].append("mins")
units["seconds"].append("secs")


class HumanTime:
    calendar = pdt.Calendar(version=pdt.VERSION_CONTEXT_STYLE)

    def __init__(self, argument):
        now = datetime.utcnow()
        dt, status = self.calendar.parseDT(argument, sourceTime=now)
        if not status.hasDateOrTime:
            raise BadArgument('Invalid time provided, try e.g. "tomorrow" or "3 days".')

        if not status.hasTime:
            # replace it with the current time
            dt = dt.replace(
                hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond
            )

        self.dt = dt
        self._past = dt < now


class Time(HumanTime):
    def __init__(self, argument):
        try:
            short_time = ShortTime(argument)
        except Exception:
            super().__init__(argument)
        else:
            self.dt = short_time.dt
            self._past = False


class FutureTime(Time):
    def __init__(self, argument):
        super().__init__(argument)

        if self._past:
            raise BadArgument("The time is in the past.")


class UserFriendlyTimeSync(Converter):
    """That way quotes aren't absolutely necessary."""

    def __init__(self):
        self.raw: str = None
        self.dt: datetime = None
        self.arg = None
        self.now: datetime = None

    def check_constraints(self, now, remaining):
        if self.dt < now:
            raise BadArgument("This time is in the past.")

        self.arg = remaining
        return self

    def convert(self, ctx, argument):
        self.raw = argument
        remaining = ""
        try:
            calendar = HumanTime.calendar
            regex = ShortTime.compiled
            self.dt = self.now = datetime.utcnow()

            match = regex.match(argument)
            if match is not None and match.group(0):
                data = {k: int(v) for k, v in match.groupdict(default="0").items()}
                remaining = argument[match.end() :].strip()
                self.dt = self.now + relativedelta(**data)
                return self.check_constraints(self.now, remaining)

            # apparently nlp does not like "from now"
            # it likes "from x" in other cases though
            # so let me handle the 'now' case
            if argument.endswith(" from now"):
                argument = argument[:-9].strip()
            # handles "in xxx hours"
            if argument.startswith("in "):
                argument = argument[3:].strip()

            elements = calendar.nlp(argument, sourceTime=self.now)
            if elements is None or not elements:
                return self.check_constraints(self.now, argument)

            # handle the following cases:
            # "date time" foo
            # date time foo
            # foo date time

            # first the first two cases:
            dt, status, begin, end, _ = elements[0]

            if not status.hasDateOrTime:
                return self.check_constraints(self.now, argument)

            if begin not in (0, 1) and end != len(argument):
                raise BadArgument(
                    "Time is either in an inappropriate location, which must "
                    "be either at the end or beginning of your input, or I "
                    "just flat out did not understand what you meant. Sorry."
                )

            if not status.hasTime:
                # replace it with the current time
                dt = dt.replace(
                    hour=self.now.hour,
                    minute=self.now.minute,
                    second=self.now.second,
                    microsecond=self.now.microsecond,
                )

            # if midnight is provided, just default to next day
            if status.accuracy == pdt.pdtContext.ACU_HALFDAY:
                dt = dt.replace(day=self.now.day + 1)

            self.dt = dt

            if begin in (0, 1):
                if begin == 1:
                    # check if it's quoted:
                    if argument[0] != '"':
                        raise BadArgument("Expected quote before time input...")

                    if not (end < len(argument) and argument[end] == '"'):
                        raise BadArgument("If the time is quoted, you must unquote it.")

                    remaining = argument[end + 1 :].lstrip(" ,.!")
                else:
                    remaining = argument[end:].lstrip(" ,.!")
            elif len(argument) == end:
                remaining = argument[:begin].strip()

            return self.check_constraints(self.now, remaining)
        except Exception:
            logger.exception("Something went wrong while parsing the time.")
            raise


class UserFriendlyTime(UserFriendlyTimeSync):
    async def convert(self, ctx, argument):
        return super().convert(ctx, argument)


def human_timedelta(dt, *, source=None):
    now = source or datetime.utcnow()
    if dt > now:
        delta = relativedelta(dt, now)
        suffix = ""
    else:
        delta = relativedelta(now, dt)
        suffix = " ago"

    if delta.microseconds and delta.seconds:
        delta = delta + relativedelta(seconds=+1)

    attrs = ["years", "months", "days", "hours", "minutes", "seconds"]

    output = []
    for attr in attrs:
        elem = getattr(delta, attr)
        if not elem:
            continue

        if elem > 1:
            output.append(f"{elem} {attr}")
        else:
            output.append(f"{elem} {attr[:-1]}")

    if not output:
        return "now"
    if len(output) == 1:
        return output[0] + suffix
    if len(output) == 2:
        return f"{output[0]} and {output[1]}{suffix}"
    return f"{output[0]}, {output[1]} and {output[2]}{suffix}"
