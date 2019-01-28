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
        if (self.bot.self_hosted and
                self.bot.config.get('github_access_token')) or \
                self.bot.config.get('modmail_api_token'):
            return await func(self, ctx, *args, **kwargs)

        if not self.bot.self_hosted:
            desc = ('You can only use this command if you have a '
                    'configured `MODMAIL_API_TOKEN`. Get your '
                    'token from https://dashboard.modmail.tk')
        else:
            desc = ('You can only use this command if you have a '
                    'configured `GITHUB_ACCESS_TOKEN`. Get a '
                    'personal access token from developer settings.')
        embed = Embed(color=Color.red(),
                      title='Unauthorized',
                      description=desc)
        await ctx.send(embed=embed)

    return wrapper


def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        allowed = [int(x) for x in
                   str(ctx.bot.config.get('owners', '0')).split(',')]
        return ctx.author.id in allowed

    return commands.check(predicate)
