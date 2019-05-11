import functools

from discord import Embed, Color
from discord.ext import commands


def trigger_typing(func):
    @functools.wraps(func)
    async def wrapper(self, ctx: commands.Context, *args, **kwargs):
        await ctx.trigger_typing()
        return await func(self, ctx, *args, **kwargs)

    return wrapper


def github_access_token_required(func):
    @functools.wraps(func)
    async def wrapper(self, ctx: commands.Context, *args, **kwargs):
        if self.bot.config.get('github_access_token'):
            return await func(self, ctx, *args, **kwargs)

        desc = ('You can only use this command if you have a '
                'configured `GITHUB_ACCESS_TOKEN`. Get a '
                'personal access token from developer settings.')
        embed = Embed(color=Color.red(),
                      title='Unauthorized',
                      description=desc)
        await ctx.send(embed=embed)

    return wrapper
