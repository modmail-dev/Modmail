import json
import logging
import os
import re
import sys
import _string

from difflib import get_close_matches
from enum import IntEnum
from logging import FileHandler, StreamHandler, Handler
from logging.handlers import RotatingFileHandler
from string import Formatter
from typing import Dict, Optional

import discord
from discord.ext import commands


try:
    from colorama import Fore, Style
except ImportError:
    Fore = Style = type("Dummy", (object,), {"__getattr__": lambda self, item: ""})()


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


class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.

    Parameters
    ----------
    fmt_dict : Optional[Dict[str, str]]
        {key: logging format attribute} pairs. Defaults to {"message": "message"}.
    time_format: str
        time.strftime() format string. Default: "%Y-%m-%dT%H:%M:%S"
    msec_format: str
        Microsecond formatting. Appended at the end. Default: "%s.%03dZ"
    """

    def __init__(
        self,
        fmt_dict: Optional[Dict[str, str]] = None,
        time_format: str = "%Y-%m-%dT%H:%M:%S",
        msec_format: str = "%s.%03dZ",
    ):
        self.fmt_dict: Dict[str, str] = fmt_dict if fmt_dict is not None else {"message": "message"}
        self.default_time_format: str = time_format
        self.default_msec_format: str = msec_format
        self.datefmt: Optional[str] = None

    def usesTime(self) -> bool:
        """
        Overwritten to look for the attribute in the format dict values instead of the fmt string.
        """
        return "asctime" in self.fmt_dict.values()

    def formatMessage(self, record) -> Dict[str, str]:
        """
        Overwritten to return a dictionary of the relevant LogRecord attributes instead of a string.
        KeyError is raised if an unknown attribute is provided in the fmt_dict.
        """
        return {fmt_key: record.__dict__[fmt_val] for fmt_key, fmt_val in self.fmt_dict.items()}

    def format(self, record) -> str:
        """
        Mostly the same as the parent's class method, the difference being that a dict is manipulated and dumped as JSON
        instead of a string.
        """
        record.message = record.getMessage()

        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)

        message_dict = self.formatMessage(record)

        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)

        if record.exc_text:
            message_dict["exc_info"] = record.exc_text

        if record.stack_info:
            message_dict["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(message_dict, default=str)


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

json_formatter = JsonFormatter(
    {
        "level": "levelname",
        "message": "message",
        "loggerName": "name",
        "processName": "processName",
        "processID": "process",
        "threadName": "threadName",
        "threadID": "thread",
        "timestamp": "asctime",
    }
)


def create_log_handler(
    filename: Optional[str] = None,
    *,
    rotating: bool = False,
    level: int = logging.DEBUG,
    mode: str = "a+",
    encoding: str = "utf-8",
    format: str = "plain",
    maxBytes: int = 28000000,
    backupCount: int = 1,
    **kwargs,
) -> Handler:
    """
    Creates a pre-configured log handler. This function is made for consistency's sake with
    pre-defined default values for parameters and formatters to pass to handler class.
    Additional keyword arguments also can be specified, just in case.

    Plugin developers should not use this and use `models.getLogger` instead.

    Parameters
    ----------
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
    format : str
        The format to output with, can either be 'json' or 'plain'. Will apply to whichever handler is created,
        based on other conditional logic.
    maxBytes : int
        The max file size before the rollover occurs. Defaults to 28000000 (28MB). Rollover occurs whenever the current
        log file is nearly `maxBytes` in length; but if either of `maxBytes` or `backupCount` is zero,
        rollover never occurs, so you generally want to set `backupCount` to at least 1.
    backupCount : int
        Max number of backup files. Defaults to 1. If this is set to zero, rollover will never occur.

    Returns
    -------
    `StreamHandler` when `filename` is `None`, otherwise `FileHandler` or `RotatingFileHandler`
    depending on the `rotating` value.
    """
    if filename is None and rotating:
        raise ValueError("`filename` must be set to instantiate a `RotatingFileHandler`.")

    if filename is None:
        handler = StreamHandler(stream=sys.stdout, **kwargs)
        formatter = log_stream_formatter
    elif not rotating:
        handler = FileHandler(filename, mode=mode, encoding=encoding, **kwargs)
        formatter = log_file_formatter
    else:
        handler = RotatingFileHandler(
            filename, mode=mode, encoding=encoding, maxBytes=maxBytes, backupCount=backupCount, **kwargs
        )
        formatter = log_file_formatter

    if format == "json":
        formatter = json_formatter

    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


logging.setLoggerClass(ModmailLogger)
log_level = logging.INFO
loggers = set()

ch = create_log_handler(level=log_level)
ch_debug: Optional[RotatingFileHandler] = None


def getLogger(name=None) -> ModmailLogger:
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.addHandler(ch)
    if ch_debug is not None:
        logger.addHandler(ch_debug)
    loggers.add(logger)
    return logger


def configure_logging(bot) -> None:
    global ch_debug, log_level, ch

    stream_log_format, file_log_format = bot.config["stream_log_format"], bot.config["file_log_format"]
    if stream_log_format == "json":
        ch.setFormatter(json_formatter)

    logger = getLogger(__name__)
    level_text = bot.config["log_level"].upper()
    logging_levels = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }
    logger.line()

    level = logging_levels.get(level_text)
    if level is None:
        level = bot.config.remove("log_level")
        logger.warning("Invalid logging level set: %s.", level_text)
        logger.warning("Using default logging level: %s.", level)
        level = logging_levels[level]
    else:
        logger.info("Logging level: %s", level_text)
    log_level = level

    logger.info("Log file: %s", bot.log_file_path)
    ch_debug = create_log_handler(bot.log_file_path, rotating=True)

    if file_log_format == "json":
        ch_debug.setFormatter(json_formatter)

    ch.setLevel(log_level)

    logger.info("Stream log format: %s", stream_log_format)
    logger.info("File log format: %s", file_log_format)

    for log in loggers:
        log.setLevel(log_level)
        log.addHandler(ch_debug)

    # Set up discord.py logging
    d_level_text = bot.config["discord_log_level"].upper()
    d_level = logging_levels.get(d_level_text)
    if d_level is None:
        d_level = bot.config.remove("discord_log_level")
        logger.warning("Invalid discord logging level set: %s.", d_level_text)
        logger.warning("Using default discord logging level: %s.", d_level)
        d_level = logging_levels[d_level]
    d_logger = logging.getLogger("discord")
    d_logger.setLevel(d_level)

    non_verbose_log_level = max(d_level, logging.INFO)
    stream_handler = create_log_handler(level=non_verbose_log_level)
    if non_verbose_log_level != d_level:
        logger.info("Discord logging level (stdout): %s.", logging.getLevelName(non_verbose_log_level))
        logger.info("Discord logging level (logfile): %s.", logging.getLevelName(d_level))
    else:
        logger.info("Discord logging level: %s.", logging.getLevelName(d_level))
    d_logger.addHandler(stream_handler)
    d_logger.addHandler(ch_debug)

    logger.debug("Successfully configured logging.")


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
