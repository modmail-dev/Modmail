from discord.ext import commands

from core.models import PermissionLevel, getLogger

logger = getLogger(__name__)


def has_permissions_predicate(permission_level: PermissionLevel = PermissionLevel.REGULAR):
    async def predicate(ctx):
        return await check_permissions(ctx, ctx.command.qualified_name)

    predicate.permission_level = permission_level
    return predicate


def has_permissions(permission_level: PermissionLevel = PermissionLevel.REGULAR):
    """
    A decorator that checks if the author has the required permissions.

    Parameters
    ----------

    permission_level : PermissionLevel
        The lowest level of permission needed to use this command.
        Defaults to REGULAR.

    Examples
    --------
    ::
        @has_permissions(PermissionLevel.OWNER)
        async def setup(ctx):
            print("Success")
    """

    return commands.check(has_permissions_predicate(permission_level))


async def check_permissions(ctx, command_name) -> bool:
    """Logic for checking permissions for a command for a user"""
    if await ctx.bot.is_owner(ctx.author):
        # Bot owner(s) (and creator) has absolute power over the bot
        return True

    permission_level = ctx.bot.command_perm(command_name)

    if permission_level is PermissionLevel.INVALID:
        logger.warning("Invalid permission level for command %s.", command_name)
        return True

    if (
        permission_level is not PermissionLevel.OWNER
        and ctx.channel.permissions_for(ctx.author).administrator
        and ctx.guild == ctx.bot.modmail_guild
    ):
        # Administrators have permission to all non-owner commands in the Modmail Guild
        logger.debug("Allowed due to administrator.")
        return True

    command_permissions = ctx.bot.config["command_permissions"]
    checkables = {*ctx.author.roles, ctx.author}

    if command_name in command_permissions:
        # -1 is for @everyone
        return -1 in command_permissions[command_name] or any(
            check.id in command_permissions[command_name] for check in checkables
        )

    level_permissions = ctx.bot.config["level_permissions"]

    for level in PermissionLevel:
        if level >= permission_level and level.name in level_permissions:
            # -1 is for @everyone
            if -1 in level_permissions[level.name] or any(
                check.id in level_permissions[level.name] for check in checkables
            ):
                return True
    return False


def thread_only():
    """
    A decorator that checks if the command
    is being ran within a Modmail thread.
    """

    async def predicate(ctx):
        """
        Parameters
        ----------
        ctx : Context
            The current discord.py `Context`.

        Returns
        -------
        Bool
            `True` if the current `Context` is within a Modmail thread.
            Otherwise, `False`.
        """
        return ctx.thread is not None

    predicate.fail_msg = "This is not a Modmail thread."
    return commands.check(predicate)
