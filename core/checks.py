from discord.ext import commands


def has_permissions(**perms):
    """
    A decorator that checks if the author has the required permissions.

    Examples
    --------
    ::
        @has_permissions(administrator=True)
        async def setup(ctx):
            print("Success")
    """

    async def predicate(ctx):
        """
        Parameters
        ----------
        ctx : Context
            The current discord.py `Context`.

        Returns
        -------
        bool
            `True` if the author is a bot owner, or
            has the ``administrator`` permission.
            Or if the author has all of the required permissions.
            Otherwise, `False`.
        """
        if await ctx.bot.is_owner(ctx.author):
            return True

        resolved = ctx.channel.permissions_for(ctx.author)

        return resolved.administrator or all(
            getattr(resolved, name, None) == value
            for name, value in perms.items()
        )

    return commands.check(predicate)


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
    return commands.check(predicate)
