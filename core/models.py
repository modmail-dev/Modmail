import logging
from enum import IntEnum

from discord import Color, Embed
from discord.ext import commands

from colorama import Fore, Style, init


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
    def __init__(self, *args, **kwargs):
        init()
        super().__init__(*args, **kwargs)

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
        return super().debug(self._debug_(msg), *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        return super().info(self._info_(msg), *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        return super().warning(self._error_(msg), *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        return super().error(self._error_(msg), *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        return super().critical(self._error_(msg), *args, **kwargs)

    def exception(self, msg, *args, exc_info=True, **kwargs):
        return super().exception(self._error_(msg), *args, exc_info, **kwargs)

    def line(self):
        super().info(Fore.BLACK + Style.BRIGHT + "-------------------------" + Style.RESET_ALL)


class _Default:
    pass


Default = _Default()
