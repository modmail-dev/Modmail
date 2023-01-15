"""
UserFriendlyTime by Rapptz
Source:
https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/time.py
"""
from __future__ import annotations

import datetime
import discord
from typing import TYPE_CHECKING, Any, Optional, Union
import parsedatetime as pdt
from dateutil.relativedelta import relativedelta
from .utils import human_join
from discord.ext import commands
from discord import app_commands
import re

# Monkey patch mins and secs into the units
units = pdt.pdtLocales["en_US"].units
units["minutes"].append("mins")
units["seconds"].append("secs")

if TYPE_CHECKING:
    from discord.ext.commands import Context
    from typing_extensions import Self


class plural:
    """https://github.com/Rapptz/RoboDanny/blob/bf7d4226350dff26df4981dd53134eeb2aceeb87/cogs/utils/formats.py#L8-L18"""

    def __init__(self, value: int):
        self.value: int = value

    def __format__(self, format_spec: str) -> str:
        v = self.value
        singular, sep, plural = format_spec.partition("|")
        plural = plural or f"{singular}s"
        if abs(v) != 1:
            return f"{v} {plural}"
        return f"{v} {singular}"


class ShortTime:
    compiled = re.compile(
        """
           (?:(?P<years>[0-9])(?:years?|y))?             # e.g. 2y
           (?:(?P<months>[0-9]{1,2})(?:months?|mo))?     # e.g. 2months
           (?:(?P<weeks>[0-9]{1,4})(?:weeks?|w))?        # e.g. 10w
           (?:(?P<days>[0-9]{1,5})(?:days?|d))?          # e.g. 14d
           (?:(?P<hours>[0-9]{1,5})(?:hours?|h))?        # e.g. 12h
           (?:(?P<minutes>[0-9]{1,5})(?:minutes?|m))?    # e.g. 10m
           (?:(?P<seconds>[0-9]{1,5})(?:seconds?|s))?    # e.g. 15s
        """,
        re.VERBOSE,
    )

    discord_fmt = re.compile(r"<t:(?P<ts>[0-9]+)(?:\:?[RFfDdTt])?>")

    dt: datetime.datetime

    def __init__(self, argument: str, *, now: Optional[datetime.datetime] = None):
        match = self.compiled.fullmatch(argument)
        if match is None or not match.group(0):
            match = self.discord_fmt.fullmatch(argument)
            if match is not None:
                self.dt = datetime.datetime.utcfromtimestamp(int(match.group("ts")), tz=datetime.timezone.utc)
                return
            else:
                raise commands.BadArgument("invalid time provided")

        data = {k: int(v) for k, v in match.groupdict(default=0).items()}
        now = now or datetime.datetime.now(datetime.timezone.utc)
        self.dt = now + relativedelta(**data)

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> Self:
        return cls(argument, now=ctx.message.created_at)


class HumanTime:
    calendar = pdt.Calendar(version=pdt.VERSION_CONTEXT_STYLE)

    def __init__(self, argument: str, *, now: Optional[datetime.datetime] = None):
        now = now or datetime.datetime.utcnow()
        dt, status = self.calendar.parseDT(argument, sourceTime=now)
        if not status.hasDateOrTime:
            raise commands.BadArgument('invalid time provided, try e.g. "tomorrow" or "3 days"')

        if not status.hasTime:
            # replace it with the current time
            dt = dt.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        self.dt: datetime.datetime = dt
        self._past: bool = dt < now

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> Self:
        return cls(argument, now=ctx.message.created_at)


class Time(HumanTime):
    def __init__(self, argument: str, *, now: Optional[datetime.datetime] = None):
        try:
            o = ShortTime(argument, now=now)
        except Exception:
            super().__init__(argument)
        else:
            self.dt = o.dt
            self._past = False


class FutureTime(Time):
    def __init__(self, argument: str, *, now: Optional[datetime.datetime] = None):
        super().__init__(argument, now=now)

        if self._past:
            raise commands.BadArgument("this time is in the past")


class BadTimeTransform(app_commands.AppCommandError):
    pass


class TimeTransformer(app_commands.Transformer):
    async def transform(self, interaction, value: str) -> datetime.datetime:
        now = interaction.created_at
        try:
            short = ShortTime(value, now=now)
        except commands.BadArgument:
            try:
                human = FutureTime(value, now=now)
            except commands.BadArgument as e:
                raise BadTimeTransform(str(e)) from None
            else:
                return human.dt
        else:
            return short.dt


# CHANGE: Added now
class FriendlyTimeResult:
    dt: datetime.datetime
    now: datetime.datetime
    arg: str

    __slots__ = ("dt", "arg", "now")

    def __init__(self, dt: datetime.datetime, now: datetime.datetime = None):
        self.dt = dt
        self.now = now

        if now is None:
            self.now = dt
        else:
            self.now = now

        self.arg = ""

    async def ensure_constraints(
        self, ctx: Context, uft: UserFriendlyTime, now: datetime.datetime, remaining: str
    ) -> None:
        if self.dt < now:
            raise commands.BadArgument("This time is in the past.")

        # CHANGE
        # if not remaining:
        #     if uft.default is None:
        #         raise commands.BadArgument("Missing argument after the time.")
        #     remaining = uft.default

        if uft.converter is not None:
            self.arg = await uft.converter.convert(ctx, remaining)
        else:
            self.arg = remaining


class UserFriendlyTime(commands.Converter):
    """That way quotes aren't absolutely necessary."""

    def __init__(
        self,
        converter: Optional[Union[type[commands.Converter], commands.Converter]] = None,
        *,
        default: Any = None,
    ):
        if isinstance(converter, type) and issubclass(converter, commands.Converter):
            converter = converter()

        if converter is not None and not isinstance(converter, commands.Converter):
            raise TypeError("commands.Converter subclass necessary.")

        self.converter: commands.Converter = converter  # type: ignore  # It doesn't understand this narrowing
        self.default: Any = default

    async def convert(self, ctx: Context, argument: str, *, now=None) -> FriendlyTimeResult:
        calendar = HumanTime.calendar
        regex = ShortTime.compiled
        if now is None:
            now = ctx.message.created_at

        match = regex.match(argument)
        if match is not None and match.group(0):
            data = {k: int(v) for k, v in match.groupdict(default=0).items()}
            remaining = argument[match.end() :].strip()
            result = FriendlyTimeResult(now + relativedelta(**data), now)
            await result.ensure_constraints(ctx, self, now, remaining)
            return result

        if match is None or not match.group(0):
            match = ShortTime.discord_fmt.match(argument)
            if match is not None:
                result = FriendlyTimeResult(
                    datetime.datetime.utcfromtimestamp(int(match.group("ts")), now, tz=datetime.timezone.utc)
                )
                remaining = argument[match.end() :].strip()
                await result.ensure_constraints(ctx, self, now, remaining)
                return result

        # apparently nlp does not like "from now"
        # it likes "from x" in other cases though so let me handle the 'now' case
        if argument.endswith("from now"):
            argument = argument[:-8].strip()

        if argument[0:2] == "me":
            # starts with "me to", "me in", or "me at "
            if argument[0:6] in ("me to ", "me in ", "me at "):
                argument = argument[6:]

        elements = calendar.nlp(argument, sourceTime=now)
        if elements is None or len(elements) == 0:
            # CHANGE
            result = FriendlyTimeResult(now)
            await result.ensure_constraints(ctx, self, now, argument)
            return result

        # handle the following cases:
        # "date time" foo
        # date time foo
        # foo date time

        # first the first two cases:
        dt, status, begin, end, dt_string = elements[0]

        if not status.hasDateOrTime:
            raise commands.BadArgument('Invalid time provided, try e.g. "tomorrow" or "3 days".')

        if begin not in (0, 1) and end != len(argument):
            raise commands.BadArgument(
                "Time is either in an inappropriate location, which "
                "must be either at the end or beginning of your input, "
                "or I just flat out did not understand what you meant. Sorry."
            )

        if not status.hasTime:
            # replace it with the current time
            dt = dt.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        # if midnight is provided, just default to next day
        if status.accuracy == pdt.pdtContext.ACU_HALFDAY:
            dt = dt.replace(day=now.day + 1)

        result = FriendlyTimeResult(dt.replace(tzinfo=datetime.timezone.utc), now)
        remaining = ""

        if begin in (0, 1):
            if begin == 1:
                # check if it's quoted:
                if argument[0] != '"':
                    raise commands.BadArgument("Expected quote before time input...")

                if not (end < len(argument) and argument[end] == '"'):
                    raise commands.BadArgument("If the time is quoted, you must unquote it.")

                remaining = argument[end + 1 :].lstrip(" ,.!")
            else:
                remaining = argument[end:].lstrip(" ,.!")
        elif len(argument) == end:
            remaining = argument[:begin].strip()

        await result.ensure_constraints(ctx, self, now, remaining)
        return result


def human_timedelta(
    dt: datetime.datetime,
    *,
    source: Optional[datetime.datetime] = None,
    accuracy: Optional[int] = 3,
    brief: bool = False,
    suffix: bool = True,
) -> str:
    now = source or datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)

    # Microsecond free zone
    now = now.replace(microsecond=0)
    dt = dt.replace(microsecond=0)

    # This implementation uses relativedelta instead of the much more obvious
    # divmod approach with seconds because the seconds approach is not entirely
    # accurate once you go over 1 week in terms of accuracy since you have to
    # hardcode a month as 30 or 31 days.
    # A query like "11 months" can be interpreted as "!1 months and 6 days"
    if dt > now:
        delta = relativedelta(dt, now)
        output_suffix = ""
    else:
        delta = relativedelta(now, dt)
        output_suffix = " ago" if suffix else ""

    attrs = [
        ("year", "y"),
        ("month", "mo"),
        ("day", "d"),
        ("hour", "h"),
        ("minute", "m"),
        ("second", "s"),
    ]

    output = []
    for attr, brief_attr in attrs:
        elem = getattr(delta, attr + "s")
        if not elem:
            continue

        if attr == "day":
            weeks = delta.weeks
            if weeks:
                elem -= weeks * 7
                if not brief:
                    output.append(format(plural(weeks), "week"))
                else:
                    output.append(f"{weeks}w")

        if elem <= 0:
            continue

        if brief:
            output.append(f"{elem}{brief_attr}")
        else:
            output.append(format(plural(elem), attr))

    if accuracy is not None:
        output = output[:accuracy]

    if len(output) == 0:
        return "now"
    else:
        if not brief:
            return human_join(output, final="and") + output_suffix
        else:
            return " ".join(output) + output_suffix


def format_relative(dt: datetime.datetime) -> str:
    return discord.utils.format_dt(dt, "R")
