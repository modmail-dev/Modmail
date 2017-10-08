'''
MIT License

Copyright (c) 2017 verixx

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

import discord
from discord.ext import commands
import asyncio
import aiohttp
import datetime
import psutil
import time
import json
import sys
import os
import re
import textwrap

class Modmail(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='m.')
        self.uptime = datetime.datetime.utcnow()
        self._add_commands()

    def _add_commands(self):
        '''Adds commands automatically'''
        for attr in dir(self):
            cmd = getattr(self, attr)
            if isinstance(cmd, commands.Command):
                self.add_command(cmd)

    @property
    def token(self):
        '''Returns your token wherever it is'''
        try:
            with open('data/config.json') as f:
                config = json.load(f)
                if config.get('TOKEN') == "your_token_here":
                    if not os.environ.get('TOKEN'):
                        self.run_wizard()
                else:
                    token = config.get('TOKEN').strip('\"')
        except FileNotFoundError:
            token = None
        return os.environ.get('TOKEN') or token

    @staticmethod
    def run_wizard():
        '''Wizard for first start'''
        print('------------------------------------------')
        token = input('Enter your token:\n> ')
        print('------------------------------------------')
        data = {
                "TOKEN" : token,
            }
        with open('data/config.json','w') as f:
            f.write(json.dumps(data, indent=4))
        print('------------------------------------------')
        print('Restarting...')
        print('------------------------------------------')
        os.execv(sys.executable, ['python'] + sys.argv)

    @classmethod
    def init(bot, token=None):
        '''Starts the actual bot'''
        selfbot = bot()
        if token:
            to_use = token.strip('"')
        else:
            to_use = selfbot.token.strip('"')
        try:
            selfbot.run(to_use, reconnect=True)
        except Exception as e:
            print(e)

    async def on_connect(self):
        print('---------------')
        print('Modmail connected!')

    async def on_ready(self):
        '''Bot startup, sets uptime.'''
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()
        print(textwrap.dedent(f'''
        ---------------
        Client is ready!
        ---------------
        Author: verixx#7220
        ---------------
        Logged in as: {self.user}
        User ID: {self.user.id}
        ---------------
        '''))

    def overwrites(self, ctx):
        '''Permision overwrites for the guild.'''
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }

        for role in self.guess_modroles(ctx):
            overwrites[role] = discord.PermissionOverwrite(read_messages=True)

        return overwrites

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        '''Sets up a server for modmail'''
        if discord.utils.get(ctx.guild.categories, name='modmail'):
            return await ctx.send('This server is already set up.')


        categ = await ctx.guild.create_category(name='modmail', overwrites=self.overwrites(ctx))
        await categ.edit(position=0)
        await ctx.send('Successfully set up server.')

    @commands.command()
    async def ping(self, ctx):
        """Pong! Returns your websocket latency."""
        em = discord.Embed()
        em.title ='Pong! Websocket Latency:'
        em.description = f'{self.ws.latency * 1000:.4f} ms'
        em.color = 0x00FF00
        await ctx.send(embed=em)

    def guess_modroles(self, ctx):
        '''Finds roles if it has the manage_guild perm'''
        for role in ctx.guild.roles:
            if role.permissions.manage_guild:
                yield role


    async def process_modmail(self, message):
        pass

    async def on_message(self, message):
        await self.process_commands(message)
        if isinstance(message.channel, discord.DMChannel):
            await self.process_modmail(message)

if __name__ == '__main__':
    Modmail.init('token')
