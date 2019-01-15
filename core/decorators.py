import functools
import discord
from discord.ext import commands
import asyncio


def trigger_typing(func):
    @functools.wraps(func)
    async def wrapper(self, ctx, *args, **kwargs):
        await ctx.trigger_typing()
        return await func(self, ctx, *args, **kwargs)
    return wrapper


def auth_required(func):
    @functools.wraps(func)
    async def wrapper(self, ctx, *args, **kwargs):
        if self.bot.selfhosted and self.bot.config.get('github_access_token') or self.bot.config.get('modmail_api_token'):
            return await func(self, ctx, *args, **kwargs)

        
        em = discord.Embed(
            color=discord.Color.red(),
            title='Unauthorized',
            description='You can only use this command if you have a configured `MODMAIL_API_TOKEN`. Get your token from https://dashboard.modmail.tk' if not self.bot.selfhosted else 'You can only use this command if you have a configured `GITHUB_ACCESS_TOKEN`. Get a personal access token from developer settings.'
        )
        await ctx.send(embed=em)
    return wrapper


def owner_only():
    async def predicate(ctx):
        allowed = [int(x) for x in str(ctx.bot.config.get('owners', '0')).split(',')]
        return ctx.author.id in allowed
    return commands.check(predicate)


def asyncexecutor(loop=None, executor=None):
    loop = loop or asyncio.get_event_loop()

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            partial = functools.partial(func, *args, **kwargs)
            return loop.run_in_executor(executor, partial)
        return wrapper
    return decorator
