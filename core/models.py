from enum import IntEnum

from discord import Color, Embed
from discord.ext import commands


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
