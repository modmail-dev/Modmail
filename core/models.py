import logging
import re
import sys
import os
from enum import IntEnum
from logging.handlers import RotatingFileHandler
from string import Formatter

import discord
from discord.ext import commands

import _string

try:
    from colorama import Fore, Style
except ImportError:
    Fore = Style = type("Dummy", (object,), {"__getattr__": lambda self, item: ""})()


if ".heroku" in os.environ.get("PYTHONHOME", ""):
    # heroku
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
        # Single reference of Color.red()
        return discord.Embed(title="Error", description=self.msg, color=discord.Color.red())


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


logging.setLoggerClass(ModmailLogger)
log_level = logging.INFO
loggers = set()

ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(log_level)
formatter = logging.Formatter(
    "%(asctime)s %(name)s[%(lineno)d] - %(levelname)s: %(message)s", datefmt="%m/%d/%y %H:%M:%S"
)
ch.setFormatter(formatter)

ch_debug = None


def getLogger(name=None) -> ModmailLogger:
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.addHandler(ch)
    if ch_debug is not None:
        logger.addHandler(ch_debug)
    loggers.add(logger)
    return logger


class FileFormatter(logging.Formatter):
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

    def format(self, record):
        record.msg = self.ansi_escape.sub("", record.msg)
        return super().format(record)


def configure_logging(name, level=None):
    global ch_debug, log_level
    ch_debug = RotatingFileHandler(name, mode="a+", maxBytes=48000, backupCount=1, encoding="utf-8")

    formatter_debug = FileFormatter(
        "%(asctime)s %(name)s[%(lineno)d] - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch_debug.setFormatter(formatter_debug)
    ch_debug.setLevel(logging.DEBUG)

    if level is not None:
        log_level = level

    ch.setLevel(log_level)

    for logger in loggers:
        logger.setLevel(log_level)
        logger.addHandler(ch_debug)


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

            def check(c):
                return isinstance(c, discord.CategoryChannel) and c.name.lower().startswith(argument.lower())

            if guild:
                result = discord.utils.find(check, guild.categories)
            else:
                result = discord.utils.find(check, bot.get_all_channels())

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
