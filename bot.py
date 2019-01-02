'''
MIT License

Copyright (c) 2017 Kyb3r

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

__version__ = '2.0.0'

from contextlib import redirect_stdout
from urllib.parse import urlparse
from copy import deepcopy
import functools
import asyncio
import textwrap
import traceback
import datetime
import inspect
import string
import time
import json
import os
import re
import io

from colorama import init, Fore, Back, Style
import dateutil.parser

init()

from discord.ext import commands
import discord
import aiohttp

from core.paginator import PaginatorSession
from core.api import Github, ModmailApiClient
from core.thread import ThreadManager, Thread

line = Fore.BLACK + Style.BRIGHT + '-------------------------' + Style.RESET_ALL

class ModmailBot(commands.Bot):

    '''Commands directly related to Modmail functionality.'''

    def __init__(self):
        super().__init__(command_prefix=self.get_pre)
        self.start_time = datetime.datetime.utcnow()
        self.threads = ThreadManager(self) 
        self.data_task = self.loop.create_task(self.data_loop())
        
        self._add_commands()

    def _add_commands(self):
        '''Adds commands automatically'''
        self.remove_command('help')

        print(line + Fore.CYAN)
        print('┌┬┐┌─┐┌┬┐┌┬┐┌─┐┬┬',
              '││││ │ │││││├─┤││',
              '┴ ┴└─┘─┴┘┴ ┴┴ ┴┴┴─┘', sep='\n')
        print(f'v{__version__}')
        print('Author: kyb3r' + Style.RESET_ALL)
        print(line + Fore.CYAN)

        for attr in dir(self):
            cmd = getattr(self, attr)
            if isinstance(cmd, commands.Command):
                self.add_command(cmd)

        for file in os.listdir('cogs'):
            if not file.endswith('.py'):
                continue
            cog = f'cogs.{file[:-3]}'
            print(f'Loading {cog}')
            self.load_extension(cog)
        
    async def logout(self):
        await self.session.close()
        self.data_task.cancel()
        await super().logout()
    
    def run(self):
        try:
            super().run(self.token)
        finally:
            print(Fore.CYAN + ' Shutting down bot' + Style.RESET_ALL)

    @property
    def config(self):
        try:
            with open('config.json') as f:
                config = json.load(f)
        except FileNotFoundError:
            config = {}
        config.update(os.environ)
        return config
    
    @property
    def snippets(self):
        return {
            key.split('_')[1].lower(): val
            for key, val in self.config.items() 
            if key.startswith('SNIPPET_')
            }

    @property
    def token(self):
        return self.config.get('TOKEN')

    @property
    def guild_id(self):
        return int(self.config.get('GUILD_ID'))
    
    @property
    def guild(self):
        return discord.utils.get(self.guilds, id=self.guild_id)

    @property
    def main_category(self):
        if self.guild:
            return discord.utils.get(self.guild.categories, name='Mod Mail')

    @property
    def blocked_users(self):
        if self.guild:
            top_chan = self.main_category.channels[0]
            return [int(i) for i in re.findall(r'\d+', top_chan.topic)]

    @staticmethod
    async def get_pre(bot, message):
        '''Returns the prefix.'''
        p = bot.config.get('PREFIX') or 'm.'
        return [p, f'<@{bot.user.id}> ', f'<@!{bot.user.id}> ']

    async def on_connect(self):
        print(line)
        print(Fore.CYAN + 'Connected to gateway.')
        
        self.session = aiohttp.ClientSession()
        self.modmail_api = ModmailApiClient(self) 
        status = os.getenv('STATUS') or self.config.get('STATUS')
        if status:
            await self.change_presence(activity=discord.Game(status))

    async def on_ready(self):
        '''Bot startup, sets uptime.'''
        print(textwrap.dedent(f'''
        {line}
        {Fore.CYAN}Client ready.
        {line}
        {Fore.CYAN}Logged in as: {self.user}
        {Fore.CYAN}User ID: {self.user.id}
        {Fore.CYAN}Guild ID: {self.guild.id if self.guild else 0}
        {line}
        ''').strip())
        
        await self.threads.populate_cache()

    async def process_modmail(self, message):
        '''Processes messages sent to the bot.'''

        reaction = '🚫' if message.author.id in self.blocked_users else '✅'

        try:
            await message.add_reaction(reaction)
        except:
            pass

        blocked_em = discord.Embed(
            title='Message not sent!', 
            color=discord.Color.red(),
            description='You have been blocked from using modmail.'
            )

        if str(message.author.id) in self.blocked_users:
            await message.author.send(embed=blocked_em)
        else:
            thread = await self.threads.find_or_create(message.author)
            await thread.send(message)

    async def on_message(self, message):
        if message.author.bot:
            return
        if isinstance(message.channel, discord.DMChannel):
            return await self.process_modmail(message)

        prefix = self.config.get('PREFIX', 'm.')

        if message.content.startswith(prefix):
            cmd = message.content[len(prefix):].strip()
            if cmd in self.snippets:
                message.content = f'{prefix}reply {self.snippets[cmd]}'
                
        await self.process_commands(message)
    
    async def on_message_delete(self, message):
        '''Support for deleting linked messages'''
        if message.embeds and not isinstance(message.channel, discord.DMChannel):
            matches = re.findall(r'Moderator - (\d+)', str(message.embeds[0].footer.text))
            if matches:
                thread = await self.threads.find(channel=message.channel)

                channel = thread.recipient.dm_channel
                message_id = matches[0]

                async for msg in channel.history():
                    if msg.embeds and f'Moderator - {message_id}' in msg.embeds[0].footer.text:
                        return await msg.delete()
    
    async def on_message_edit(self, before, after):
        if before.author.bot:
            return
        if isinstance(before.channel, discord.DMChannel):
            channel = await self.find_or_create_thread(before.author)
            async for msg in channel.history():
                if msg.embeds:
                    embed = msg.embeds[0]
                    if f'User - {before.id}' in embed.footer.text:
                        if ' - (Edited)' not in embed.footer.text:
                            embed.set_footer(text=embed.footer.text + ' - (Edited)')
                        embed.description = after.content
                        await msg.edit(embed=embed)
                        break
    
    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.UserInputError)):
            await ctx.invoke(self.get_command('help'), command=str(ctx.command))
        else:
            raise error

    def overwrites(self, ctx):
        '''Permision overwrites for the guild.'''
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }

        for role in ctx.guild.roles:
            if role.permissions.manage_guild:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True)

        return overwrites
    
    async def data_loop(self):
        await self.wait_until_ready()

        while True:
            data = {
                "bot_id": self.user.id,
                "bot_name": str(self.user),
                "guild_id": self.guild_id,
                "guild_name": self.guild.name,
                "member_count": len(self.guild.members),
                "uptime": (datetime.datetime.utcnow() - self.start_time).total_seconds(),
                "version": __version__
            }

            await self.session.post('https://api.modmail.tk/metadata', json=data)

            await asyncio.sleep(3600)

    async def get_latest_updates(self, limit=3):
        latest_commits = ''

        async for commit in Github(self).get_latest_commits(limit=limit):

            short_sha = commit['sha'][:6]
            html_url = commit['html_url']
            message = commit['commit']['message'].splitlines()[0]
            author_name = commit['author']['login']

            latest_commits += f'[`{short_sha}`]({html_url}) {message} - {author_name}\n'

        return latest_commits

    @property
    def uptime(self):
        now = datetime.datetime.utcnow()
        delta = now - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        fmt = '{h}h {m}m {s}s'
        if days:
            fmt = '{d}d ' + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

if __name__ == '__main__':
    bot = ModmailBot()
    bot.run()
