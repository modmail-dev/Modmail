import logging

from discord.ext import commands

from core.models import PermissionLevel
from core.utils import error

logger = logging.getLogger("Modmail")


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

    async def predicate(ctx):
        has_perm = await check_permissions(
            ctx, ctx.command.qualified_name, permission_level
        )

        if not has_perm and ctx.command.qualified_name != "help":
            logger.error(
                error(
                    f"You does not have permission to use this command: "
                    f"`{ctx.command.qualified_name}` ({permission_level.name})."
                )
            )
        return has_perm

    predicate.permission_level = permission_level
    return commands.check(predicate)


async def check_permissions(ctx, command_name, permission_level) -> bool:
    """Logic for checking permissions for a command for a user"""
    if await ctx.bot.is_owner(ctx.author):
        # Direct bot owner (creator) has absolute power over the bot
        return True

    if (
        permission_level != PermissionLevel.OWNER
        and ctx.channel.permissions_for(ctx.author).administrator
    ):
        # Administrators have permission to all non-owner commands
        return True

    command_permissions = ctx.bot.config.command_permissions
    author_roles = ctx.author.roles

    if command_name in command_permissions:
        # -1 is for @everyone
        if -1 in command_permissions[command_name]:
            return True
        has_perm_role = any(
            role.id in command_permissions[command_name] for role in author_roles
        )
        has_perm_id = ctx.author.id in command_permissions[command_name]
        return has_perm_role or has_perm_id

    level_permissions = ctx.bot.config.level_permissions

    for level in PermissionLevel:
        if level >= permission_level and level.name in level_permissions:
            if -1 in level_permissions[level.name]:
                return True
            has_perm_role = any(
                role.id in level_permissions[level.name] for role in author_roles
            )
            has_perm_id = ctx.author.id in level_permissions[level.name]
            if has_perm_role or has_perm_id:
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
