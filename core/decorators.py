import functools
import discord
from discord.ext import commands

def trigger_typing(func):
    @functools.wraps(func)
    async def wrapper(self, ctx, *args, **kwargs):
        await ctx.trigger_typing()
        return await func(self, ctx, *args, **kwargs)
    return wrapper

def auth_required(func):
    @functools.wraps(func)
    async def wrapper(self, ctx, *args, **kwargs):
        if self.bot.config.get('MODMAIL_API_TOKEN'):
            return await func(self, ctx, *args, **kwargs)
        em = discord.Embed(
            color=discord.Color.red(),
            title='Unauthorized',
            description='You can only use this command if you have a configured `MODMAIL_API_TOKEN`. Get your token from https://dashboard.modmail.tk'
            )
        await ctx.send(embed=em)
    return wrapper 

def owner_only():
    async def predicate(ctx):
        allowed = [int(x) for x in ctx.bot.config.get('OWNERS', '0').split(',')]
        return ctx.author.id in allowed
    return commands.check(predicate)