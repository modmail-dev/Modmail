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

GUILD_ID = 0 # your guild id here

import discord
from discord.ext import commands
import asyncio
import textwrap
import datetime
import time
import json
import sys
import os
import string


class Modmail(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=self.get_pre)
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
            with open('config.json') as f:
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
    async def get_pre(bot, message):
        '''Returns the prefix.'''
        with open('config.json') as f:
            prefix = json.load(f).get('PREFIX')
        return os.environ.get('PREFIX') or prefix or 'm.'

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
    def init(cls, token=None):
        '''Starts the actual bot'''
        bot = cls()
        if token:
            to_use = token.strip('"')
        else:
            to_use = bot.token.strip('"')
        try:
            bot.run(to_use, reconnect=True)
        except Exception as e:
            raise e

    async def on_connect(self):
        print('---------------')
        print('Modmail connected!')
        game = discord.Game(name='Contact Vault-Tec!')
        await self.change_presence(game=game)

    @property
    def guild_id(self):
        from_heroku = os.environ.get('GUILD_ID')
        return int(from_heroku) if from_heroku else GUILD_ID

    async def on_ready(self):
        '''Bot startup, sets uptime.'''
        self.guild = discord.utils.get(self.guilds, id=self.guild_id)
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

    def overwrites(self, ctx, modrole=None):
        '''Permision overwrites for the guild.'''
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }

        if modrole:
            overwrites[modrole] = discord.PermissionOverwrite(read_messages=True)
        else:
            for role in self.guess_modroles(ctx):
                overwrites[role] = discord.PermissionOverwrite(read_messages=True)

        return overwrites

    def help_embed(self):
        em = discord.Embed(color=0x00FFFF)
        em.set_author(name='Mod Mail - Help', icon_url=self.user.avatar_url)
        em.description = 'This bot is a python implementation of a stateless "Mod Mail" bot. ' \
                         'Made by verixx and improved by the suggestions of others. This bot ' \
                         'saves no data and utilises channel topics for storage and syncing.' 
                 

        cmds = '`m.setup [modrole] <- (optional)` - Command that sets up the bot.\n' \
               '`m.reply <message...>` - Sends a message to the current thread\'s recipient.\n' \
               '`m.close` - Closes the current thread and deletes the channel.\n' \
               '`m.disable` - Closes all threads and disables modmail for the server.\n' \
               '`m.customstatus` - Sets the Bot status to whatever you want.'

        warn = 'Do not manually delete the category or channels as it will break the system. ' \
               'Modifying the channel topic will also break the system.'
        em.add_field(name='Commands', value=cmds)
        em.add_field(name='Warning', value=warn)
        em.add_field(name='Github', value='https://github.com/verixx/modmail')
        em.set_footer(text='Star the repository to unlock hidden features!')

        return em

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx, *, modrole: discord.Role=None):
        '''Sets up a server for modmail'''
        if discord.utils.get(ctx.guild.categories, name='Mod Mail'):
            return await ctx.send('This server is already set up.')

        categ = await ctx.guild.create_category(
            name='Mod Mail', 
            overwrites=self.overwrites(ctx, modrole=modrole)
            )
        await categ.edit(position=0)
        c = await ctx.guild.create_text_channel(name='bot-info', category=categ)
        await c.send(embed=self.help_embed())
        await ctx.send('Successfully set up server.')

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def disable(self, ctx):
        '''Close all threads and disable modmail.'''
        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        if not categ:
            return await ctx.send('This server is not set up.')
        for category, channels in ctx.guild.by_category():
            if category == categ:
                for chan in channels:
                    if 'User ID:' in str(chan.topic):
                        user_id = int(chan.topic.split(': ')[1])
                        user = self.get_user(user_id)
                        await user.send(f'**{ctx.author}** has closed this modmail session.')
                    await chan.delete()
        await categ.delete()
        await ctx.send('Disabled modmail.')


    @commands.command(name='close')
    @commands.has_permissions(manage_guild=True)
    async def _close(self, ctx):
        if 'User ID:' not in str(ctx.channel.topic):
            return await ctx.send('This is not a modmail thread.')
        user_id = int(ctx.channel.topic.split(': ')[1])
        user = self.get_user(user_id)
        em = discord.Embed(title='Thread Closed')
        em.description = f'**{ctx.author}** has closed this modmail session.'
        em.color = discord.Color.red()
        try:
            await user.send(embed=em)
        except:
            pass
        await ctx.channel.delete()

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

    def format_info(self, user):
        '''Get information about a member of a server
        supports users from the guild or not.'''
        server = self.guild
        member = self.guild.get_member(user.id)
        avi = user.avatar_url
        time = datetime.datetime.utcnow()
        desc = 'Modmail thread started.'
        color = 0

        if member:
            roles = sorted(member.roles, key=lambda c: c.position)
            rolenames = ', '.join([r.name for r in roles if r.name != "@everyone"]) or 'None'
            member_number = sorted(server.members, key=lambda m: m.joined_at).index(member) + 1
            for role in roles:
                if str(role.color) != "#000000":
                    color = role.color

        em = discord.Embed(colour=color, description=desc, timestamp=time)

        em.add_field(name='Account Created', value=str((time - user.created_at).days)+' days ago.')
        em.set_footer(text='User ID: '+str(user.id))
        em.set_thumbnail(url=avi)
        em.set_author(name=user, icon_url=server.icon_url)

        if member:
            em.add_field(name='Joined', value=str((time - member.joined_at).days)+' days ago.')
            em.add_field(name='Member No.',value=str(member_number),inline = True)
            em.add_field(name='Nick', value=member.nick, inline=True)
            em.add_field(name='Roles', value=rolenames, inline=True)

        return em

    async def send_mail(self, message, channel, mod):
        author = message.author
        fmt = discord.Embed()
        fmt.description = message.content
        fmt.timestamp = message.created_at
        if mod:
            fmt.color=discord.Color.green()
            fmt.set_author(name=str(author), icon_url=author.avatar_url)
            fmt.set_footer(text='Moderator')
        else:
            fmt.color=discord.Color.gold()
            fmt.set_author(name=str(author), icon_url=author.avatar_url)
            fmt.set_footer(text='User')
        embed = None
        if message.attachments:
            fmt.set_image(url=message.attachments[0].url)
        await channel.send(embed=fmt)

    async def process_reply(self, message):
        try:
            await message.delete()
        except discord.errors.NotFound:
            pass
        await self.send_mail(message, message.channel, mod=True)
        user_id = int(message.channel.topic.split(': ')[1])
        user = self.get_user(user_id)
        await self.send_mail(message, user, mod=True)

    def format_name(self, author):
        name = author.name
        new_name = ''
        for letter in name:
            if letter in string.ascii_letters + string.digits:
                new_name += letter
        if not new_name:
            new_name = 'null'
        new_name += f'-{author.discriminator}'
        return new_name

    async def process_modmail(self, message):
        try:
            await message.add_reaction('✅')
        except:
            pass
        guild = self.guild
        author = message.author
        topic = f'User ID: {author.id}'
        channel = discord.utils.get(guild.text_channels, topic=topic)
        categ = discord.utils.get(guild.categories, name='Mod Mail')

        em = discord.Embed(title='ROBCO INDUSTRIES UNIFIED OPERATING SYSTEM')
        em.description = 'Vault-Tec has recieved your query, please be patient and a representative will get back to you as soon as possible!'
        em.color = discord.Color.green()

        if channel is not None:
            await self.send_mail(message, channel, mod=False)
        else:
            await message.author.send(embed=em)
            channel = await guild.create_text_channel(
                name=self.format_name(author),
                category=categ
                )
            await channel.edit(topic=topic)
            await channel.send('@here', embed=self.format_info(author))
            await channel.send('\u200b')
            await self.send_mail(message, channel, mod=False)

    async def on_message(self, message):
        if message.author.bot:
            return
        await self.process_commands(message)
        if isinstance(message.channel, discord.DMChannel):
            await self.process_modmail(message)

    @commands.command()
    async def reply(self, ctx, *, msg):
        categ = discord.utils.get(ctx.guild.categories, id=ctx.channel.category_id)
        if categ is not None:
            if categ.name == 'Mod Mail':
                if 'User ID:' in ctx.channel.topic:
                    ctx.message.content = msg
                    await self.process_reply(ctx.message)

    @commands.command(name="customstatus", aliases=['status', 'presence'])
    @commands.has_permissions(administrator=True)
    async def _status(self, ctx, *, message):
        await self.change_presence(game=discord.Game(name=message), status=discord.Status.online)
        await ctx.send(f"Changed status to **{message}**")

    @commands.command()
    async def block(self, ctx):
        categ = discord.utils.get(ctx.guild.categories, id=ctx.channel.category_id)
        if categ is not None:
            if categ.name == 'Mod Mail':
                await self.get_user(int(ctx.channel.topic.split(': ')[1])).block()
                await ctx.channel.delete()
                
if __name__ == '__main__':
    Modmail.init()
