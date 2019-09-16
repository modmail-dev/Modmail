import _string
import logging
from enum import IntEnum
from string import Formatter

from discord import Color, Embed
from discord.ext import commands

try:
    from colorama import Fore, Style
except ImportError:
    Fore = Style = type("Dummy", (object,), {"__getattr__": lambda self, item: ""})()


class PermissionLevel(IntEnum):
    OWNER = 5
    ADMINISTRATOR = 4
    ADMIN = 4
    MODERATOR = 3
    MOD = 3
    SUPPORTER = 2
    RESPONDER = 2
    REGULAR = 1
    INVALID = -1


class InvalidConfigError(commands.BadArgument):
    def __init__(self, msg, *args):
        super().__init__(msg, *args)
        self.msg = msg

    @property
    def embed(self):
        return Embed(title="Error", description=self.msg, color=Color.red())


class ModmailLogger(logging.Logger):
    @staticmethod
    def _debug_(*msgs):
        return f'{Fore.CYAN}{" ".join(msgs)}{Style.RESET_ALL}'

    @staticmethod
    def _info_(*msgs):
        return f'{Fore.GREEN}{" ".join(msgs)}{Style.RESET_ALL}'

    @staticmethod
    def _error_(*msgs):
        return f'{Fore.RED}{" ".join(msgs)}{Style.RESET_ALL}'

    def debug(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.DEBUG):
            self._log(logging.DEBUG, self._debug_(msg), args, **kwargs)

    def info(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.INFO):
            self._log(logging.INFO, self._info_(msg), args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.WARNING):
            self._log(logging.WARNING, self._error_(msg), args, **kwargs)

    def error(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.ERROR):
            self._log(logging.ERROR, self._error_(msg), args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.CRITICAL):
            self._log(logging.CRITICAL, self._error_(msg), args, **kwargs)

    def exception(self, msg, *args, exc_info=True, **kwargs):
        self.error(msg, *args, exc_info=exc_info, **kwargs)

    def line(self):
        if self.isEnabledFor(logging.INFO):
            self._log(
                logging.INFO,
                Fore.BLACK
                + Style.BRIGHT
                + "-------------------------"
                + Style.RESET_ALL,
                [],
            )


class _Default:
    pass


Default = _Default()


class SafeFormatter(Formatter):

    def get_field(self, field_name, args, kwargs):
        first, rest = _string.formatter_field_name_split(field_name)

        try:
            obj = self.get_value(first, args, kwargs)
        except (IndexError, KeyError):
            return "<Invalid>", first

        # loop through the rest of the field_name, doing
        #  getattr or getitem as needed
        # stops when reaches the depth of 2 or starts with _.
        try:
            for n, (is_attr, i) in enumerate(rest):
                if n >= 2:
                    break
                if is_attr:
                    if str(i).startswith('_'):
                        break
                    obj = getattr(obj, i)
                else:
                    obj = obj[i]
            else:
                return obj, first
        except (IndexError, KeyError):
            pass
        return "<Invalid>", first
