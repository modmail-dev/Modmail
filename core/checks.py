from discord.ext import commands

def has_permissions(**perms):
    """Check if the author has required permissions.
    This will always return ``True`` if the author is a bot owner, or
    has the ``administrator`` permission.
    """
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True

        resolved = ctx.channel.permissions_for(ctx.author)

        return resolved.administrator or all(
            getattr(resolved, name, None) == value for name, value in perms.items()
        )
    
    return commands.check(predicate)

def thread_only():
    """Checks if the command is being run in a modmail thread"""
    async def predicate(ctx):
        return ctx.thread is not None
    return commands.check(predicate)