import logging
import os
import re
import sys

from logging import FileHandler, StreamHandler
from logging.handlers import RotatingFileHandler
from typing import Optional, Union


try:
    from colorama import Fore, Style, init as color_init
except ImportError:
    Fore = Style = type("Dummy", (object,), {"__getattr__": lambda self, item: ""})()
else:
    color_init()


if ".heroku" in os.environ.get("PYTHONHOME", ""):
    # heroku
    Fore = Style = type("Dummy", (object,), {"__getattr__": lambda self, item: ""})()


class ModmailLogger(logging.Logger):
    @staticmethod
    def _debug_(*msgs):
        return f'{Fore.CYAN}{" ".join(msgs)}{Style.RESET_ALL}'

    @staticmethod
    def _info_(*msgs):
        return f'{Fore.LIGHTMAGENTA_EX}{" ".join(msgs)}{Style.RESET_ALL}'

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

    def line(self, level="info"):
        if level == "info":
            level = logging.INFO
        elif level == "debug":
            level = logging.DEBUG
        else:
            level = logging.INFO
        if self.isEnabledFor(level):
            self._log(
                level,
                Fore.BLACK + Style.BRIGHT + "-------------------------" + Style.RESET_ALL,
                [],
            )


class FileFormatter(logging.Formatter):
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

    def format(self, record):
        record.msg = self.ansi_escape.sub("", record.msg)
        return super().format(record)


log_stream_formatter = logging.Formatter(
    "%(asctime)s %(name)s[%(lineno)d] - %(levelname)s: %(message)s", datefmt="%m/%d/%y %H:%M:%S"
)
log_file_formatter = FileFormatter(
    "%(asctime)s %(name)s[%(lineno)d] - %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def create_log_handler(
    filename: Optional[str] = None,
    *,
    rotating: bool = False,
    level: int = logging.DEBUG,
    mode: str = "a+",
    encoding: str = "utf-8",
    maxBytes: int = 48000,
    backupCount: int = 1,
    **kwargs,
) -> Union[FileHandler, RotatingFileHandler, StreamHandler]:
    """
    Return a pre-configured log handler. This function is made for consistency sake with
    pre-defined default values for parameters and formatters to pass to handler class.
    Additional keyword arguments also can be specified, just in case.

    Plugin developers should not use this and only use the `getLogger` instead to instantiate the ModmailLogger object.

    Parameters
    -----------
    filename : Optional[Path]
        Specifies that a `FileHandler` or `RotatingFileHandler` be created, using the specified filename,
        rather than a `StreamHandler`. Defaults to `None`.
    rotating : bool
        Whether the file handler should be the `RotatingFileHandler`. Defaults to `False`. Note, this
        argument only compatible if the `filename` is specified, otherwise `ValueError` will be raised.
    level : int
        The root logger level for the handler. Defaults to `logging.DEBUG`.
    mode : str
        If filename is specified, open the file in this mode. Defaults to 'a+'.
    encoding : str
        If this keyword argument is specified along with filename, its value is used when the `FileHandler` is created,
        and thus used when opening the output file. Defaults to 'utf-8'.
    maxBytes : int
        The max file size before the rollover occurs. Defaults to 48000. Rollover occurs whenever the current log file
        is nearly `maxBytes` in length; but if either of `maxBytes` or `backupCount` is zero, rollover never occurs, so you
        generally want to set `backupCount` to at least 1.
    backupCount : int
        Max number of backup files. Defaults to 1. If this is set to zero, rollover will never occur.
    """
    if filename is None and rotating:
        raise ValueError("`filename` must be set to instantiate a `RotatingFileHandler`.")

    if filename is None:
        handler = StreamHandler(stream=sys.stdout, **kwargs)
        handler.setFormatter(log_stream_formatter)
    elif not rotating:
        handler = FileHandler(filename, mode=mode, encoding=encoding, **kwargs)
        handler.setFormatter(log_file_formatter)
    else:
        handler = RotatingFileHandler(
            filename, mode=mode, encoding=encoding, maxBytes=maxBytes, backupCount=backupCount, **kwargs
        )
        handler.setFormatter(log_file_formatter)

    handler.setLevel(level)
    return handler


logging.setLoggerClass(ModmailLogger)
log_level = logging.INFO
loggers = set()
ch: StreamHandler = create_log_handler(level=log_level)
ch_debug: Optional[RotatingFileHandler] = None


def getLogger(name=None) -> ModmailLogger:
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.addHandler(ch)
    if ch_debug is not None:
        logger.addHandler(ch_debug)
    loggers.add(logger)
    return logger


def configure_logging(name, level: Optional[int] = None):
    global ch_debug, log_level
    ch_debug = create_log_handler(name, rotating=True)

    if level is not None:
        log_level = level

    ch.setLevel(log_level)

    for logger in loggers:
        logger.setLevel(log_level)
        logger.addHandler(ch_debug)


from string import Formatter
from difflib import get_close_matches
from enum import IntEnum
import _string
import discord
from discord.ext import commands


class InvalidConfigError(commands.BadArgument):
    def __init__(self, msg, *args):
        super().__init__(msg, *args)
        self.msg = msg

    @property
    def embed(self):
        # Single reference of Color.red()
        return discord.Embed(title="Error", description=self.msg, color=discord.Color.red())


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
                    if str(i).startswith("_"):
                        break
                    obj = getattr(obj, i)
                else:
                    obj = obj[i]
            else:
                return obj, first
        except (IndexError, KeyError):
            pass
        return "<Invalid>", first


class UnseenFormatter(Formatter):
    def get_value(self, key, args, kwds):
        if isinstance(key, str):
            try:
                return kwds[key]
            except KeyError:
                return "{" + key + "}"
        else:
            return super().get_value(key, args, kwds)


class SimilarCategoryConverter(commands.CategoryChannelConverter):
    async def convert(self, ctx, argument):
        bot = ctx.bot
        guild = ctx.guild

        try:
            return await super().convert(ctx, argument)
        except commands.ChannelNotFound:

            if guild:
                categories = {c.name.casefold(): c for c in guild.categories}
            else:
                categories = {
                    c.name.casefold(): c
                    for c in bot.get_all_channels()
                    if isinstance(c, discord.CategoryChannel)
                }

            result = get_close_matches(argument.casefold(), categories.keys(), n=1, cutoff=0.75)
            if result:
                result = categories[result[0]]

            if not isinstance(result, discord.CategoryChannel):
                raise commands.ChannelNotFound(argument)

        return result


class DummyMessage:
    """
    A class mimicking the original :class:discord.Message
    where all functions that require an actual message to exist
    is replaced with a dummy function
    """

    def __init__(self, message):
        if message:
            message.attachments = []
        self._message = message

    def __getattr__(self, name: str):
        return getattr(self._message, name)

    def __bool__(self):
        return bool(self._message)

    async def delete(self, *, delay=None):
        return

    async def edit(self, **fields):
        return

    async def add_reaction(self, emoji):
        return

    async def remove_reaction(self, emoji):
        return

    async def clear_reaction(self, emoji):
        return

    async def clear_reactions(self):
        return

    async def pin(self, *, reason=None):
        return

    async def unpin(self, *, reason=None):
        return

    async def publish(self):
        return

    async def ack(self):
        return


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


class DMDisabled(IntEnum):
    NONE = 0
    NEW_THREADS = 1
    ALL_THREADS = 2


class HostingMethod(IntEnum):
    HEROKU = 0
    PM2 = 1
    SYSTEMD = 2
    SCREEN = 3
    DOCKER = 4
    OTHER = 5
