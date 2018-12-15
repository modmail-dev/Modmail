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

import discord
from discord.ext import commands
from urllib.parse import urlparse
import asyncio
import textwrap
import datetime
import time
import json
import sys
import os
import re
import string
import traceback
import io
import inspect
from contextlib import redirect_stdout


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
    def config(self):
        with open('config.json') as f:
            config = json.load(f)
        config.update(os.environ)
        return config

    @property
    def token(self):
        '''Returns your token wherever it is'''
        return self.config.get('TOKEN')
    
    @staticmethod
    async def get_pre(bot, message):
        '''Returns the prefix.'''
        return bot.config.get('PREFIX') or 'm.'

    async def on_connect(self):
        print('---------------')
        print('Modmail connected!')
        status = os.getenv('STATUS') or self.config.get('STATUS')
        if status:
            print(f'Setting Status to {status}')
            await self.change_presence(activity=discord.Game(status))
        else:
            print('No status set.')

    @property
    def guild_id(self):
        return int(self.config.get('GUILD_ID'))
    
    @property
    def guild(self):
        g = discord.utils.get(self.guilds, id=self.guild_id)
        return g

    async def on_ready(self):
        '''Bot startup, sets uptime.'''
        print(textwrap.dedent(f'''
        ---------------
        Client is ready!
        ---------------
        Author: kyb3r
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

    def help_embed(self, prefix):
        em = discord.Embed(color=0x00FFFF)
        em.set_author(name='Mod Mail - Help', icon_url=self.user.avatar_url)
        em.description = 'This bot is a python implementation of a stateless "Mod Mail" bot. ' \
                         'Made by Kyb3r and improved by the suggestions of others. This bot ' \
                         'saves no data and utilises channel topics for storage and syncing.' 

        cmds = f'`{prefix}setup [modrole] <- (optional)` - Command that sets up the bot.\n' \
               f'`{prefix}reply <message...>` - Sends a message to the current thread\'s recipient.\n' \
               f'`{prefix}close` - Closes the current thread and deletes the channel.\n' \
               f'`{prefix}archive` - Closes the current thread and moves the channel to archive category.\n' \
               f'`{prefix}disable` - Closes all threads and disables modmail for the server.\n' \
               f'`{prefix}customstatus` - Sets the Bot status to whatever you want.\n' \
               f'`{prefix}block` - Blocks a user from using modmail!\n' \
               f'`{prefix}unblock` - Unblocks a user from using modmail!\n'

        warn = 'Do not manually delete the category or channels as it will break the system. ' \
               'Modifying the channel topic will also break the system. Dont break the system buddy.'

        em.add_field(name='Commands', value=cmds)
        em.add_field(name='Warning', value=warn)
        em.add_field(name='Github', value='https://github.com/kyb3r/modmail')
        em.set_footer(text='Star the repository to unlock hidden features! /s')

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
        archives = await ctx.guild.create_category(
            name='Mod Mail Archives',
            overwrites=self.overwrites(ctx, modrole=modrole)
        )
        await categ.edit(position=0)
        c = await ctx.guild.create_text_channel(name='bot-info', category=categ)
        await c.edit(topic='Manually add user id\'s to block users.\n\n'
                           'Blocked\n-------\n\n')
        await c.send(embed=self.help_embed(ctx.prefix))
        await ctx.send('Successfully set up server.')

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def disable(self, ctx, delete_archives: bool=False):
        '''Close all threads and disable modmail.'''
        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        archives = discord.utils.get(ctx.guild.categories, name='Mod Mail Archives')
        if not categ:
            return await ctx.send('This server is not set up.')
        em = discord.Embed(title='Thread Closed')
        em.description = f'**{ctx.author}** has closed this modmail session.'
        em.color = discord.Color.red()
        for category, channels in ctx.guild.by_category():
            if category == categ:
                for chan in channels:
                    if 'User ID:' in str(chan.topic):
                        user_id = int(chan.topic.split(': ')[1])
                        user = self.get_user(user_id)
                        await user.send(embed=em)
                    await chan.delete()
        await categ.delete()
        if delete_archives:
            await archives.delete()
        await ctx.send('Disabled modmail.')


    @commands.command(name='close')
    @commands.has_permissions(manage_channels=True)
    async def _close(self, ctx):
        '''Close the current thread.'''
        if 'User ID:' not in str(ctx.channel.topic):
            return await ctx.send('This is not a modmail thread.')
        user_id = int(ctx.channel.topic.split(': ')[1])
        user = self.get_user(user_id)
        em = discord.Embed(title='Thread Closed')
        em.description = f'**{ctx.author}** has closed this modmail session.'
        em.color = discord.Color.red()
        if ctx.channel.category.name != 'Mod Mail Archives': # already closed.
            try:
                await user.send(embed=em)
            except:
                pass
        await ctx.channel.delete()
    

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def archive(self, ctx):
        '''
        Archive the current thread. (Visually closes the thread
        but moves the channel into an archives category instead of 
        deleteing the channel.)
        '''
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

        archives = discord.utils.get(ctx.guild.categories, name='Mod Mail Archives')
        await ctx.channel.edit(category=archives)
        done = discord.Embed(title='Thread Archived')
        done.description = f'**{ctx.author}** has archived this modmail session.'
        done.color = discord.Color.red()
        await ctx.send(embed=done)

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

    def format_info(self, message):
        '''Get information about a member of a server
        supports users from the guild or not.'''
        user = message.author
        server = self.guild
        member = self.guild.get_member(user.id)
        avi = user.avatar_url
        time = datetime.datetime.utcnow()
        desc = f'{user.mention} has started a thread.'
        color = discord.Color.blurple()

        if member:
            roles = sorted(member.roles, key=lambda c: c.position)
            rolenames = ' '.join([r.mention for r in roles if r.name != "@everyone"])
            member_number = sorted(server.members, key=lambda m: m.joined_at).index(member) + 1
            for role in roles:
                if str(role.color) != "#000000":
                    color = role.color

        em = discord.Embed(colour=color, description=desc, timestamp=time)

        days = lambda d: (' day ago.' if d == '1' else ' days ago.')

        created = str((time - user.created_at).days)
        # em.add_field(name='Mention', value=user.mention)
        em.add_field(name='Registered', value=created + days(created))
        footer = 'User ID: '+str(user.id)
        em.set_footer(text=footer)
        em.set_thumbnail(url=avi)
        em.set_author(name=str(user), icon_url=avi)

        if member:
            joined = str((time - member.joined_at).days)
            em.add_field(name='Joined', value=joined + days(joined))
            em.add_field(name='Member No.',value=str(member_number),inline = True)
            em.add_field(name='Nickname', value=member.nick, inline=True)
            if rolenames:
                em.add_field(name='Roles', value=rolenames, inline=False)
        else:
            em.set_footer(text=footer+' | Note: this member is not part of this server.')
        
        

        return em

    async def send_mail(self, message, channel, from_mod, delete_message=True):
        author = message.author
        em = discord.Embed()
        em.description = message.content
        em.timestamp = message.created_at

        image_types = ['.png', '.jpg', '.gif', '.jpeg', '.webp']
        is_image_url = lambda u: any(urlparse(u).path.endswith(x) for x in image_types)

        delete_message = not bool(message.attachments) 
        attachments = list(filter(lambda a: not is_image_url(a.url), message.attachments))

        image_urls = [a.url for a in message.attachments]
        image_urls.extend(re.findall(r'(https?://[^\s]+)', message.content))
        image_urls = list(filter(is_image_url, image_urls))

        if image_urls:
            em.set_image(url=image_urls[0])

        if attachments:
            att = attachments[0]
            em.add_field(name='File Attachment', value=f'[{att.filename}]({att.url})')

        if from_mod:
            em.color=discord.Color.green()
            em.set_author(name=str(author), icon_url=author.avatar_url)
            em.set_footer(text='Moderator')
        else:
            em.color=discord.Color.gold()
            em.set_author(name=str(author), icon_url=author.avatar_url)
            em.set_footer(text='User')

        await channel.send(embed=em)

        if delete_message:
            try:
                await message.delete()
            except:
                pass

    async def process_reply(self, message):
        user_id = int(message.channel.topic.split(': ')[1])
        user = self.get_user(user_id)
        await asyncio.gather(
            self.send_mail(message, message.channel, from_mod=True),
            self.send_mail(message, user, from_mod=True)
        )

    def format_name(self, author, channels):
        name = author.name
        new_name = ''
        for letter in name:
            if letter in string.ascii_letters + string.digits:
                new_name += letter
        if not new_name:
            new_name = 'null'
        new_name += f'-{author.discriminator}'
        while new_name in [c.name for c in channels]:
            new_name += '-x' # two channels with same name
        return new_name

    @property
    def blocked_em(self):
        em = discord.Embed(title='Message not sent!', color=discord.Color.red())
        em.description = 'You have been blocked from using modmail.'
        return em

    async def process_modmail(self, message):
        '''Processes messages sent to the bot.'''
        try:
            await message.add_reaction('✅')
        except:
            pass

        guild = self.guild
        author = message.author
        topic = f'User ID: {author.id}'
        channel = discord.utils.get(guild.text_channels, topic=topic)
        categ = discord.utils.get(guild.categories, name='Mod Mail')
        archives = discord.utils.get(guild.categories, name='Mod Mail Archives')
        top_chan = categ.channels[0] #bot-info
        blocked = top_chan.topic.split('Blocked\n-------')[1].strip().split('\n')
        blocked = [x.strip() for x in blocked]

        if str(message.author.id) in blocked:
            return await message.author.send(embed=self.blocked_em)

        em = discord.Embed(title='Thanks for the message!')
        em.description = 'The moderation team will get back to you as soon as possible!'
        em.color = discord.Color.green()
        mention = self.config.get('MENTION') or '@here'

        if channel is not None:
            if channel.category is archives:
                await channel.edit(category=categ)
                await channel.send(mention, embed=self.format_info(message))
            await self.send_mail(message, channel, from_mod=False)
        else:
            await message.author.send(embed=em)
            channel = await guild.create_text_channel(
                name=self.format_name(author, guild.text_channels),
                category=categ
                )
            await channel.edit(topic=topic)
            await channel.send(mention, embed=self.format_info(message))
            await self.send_mail(message, channel, from_mod=False)

    async def on_message(self, message):
        if message.author.bot:
            return
        await self.process_commands(message)
        if isinstance(message.channel, discord.DMChannel):
            await self.process_modmail(message)

    @commands.command()
    async def reply(self, ctx, *, msg=''):
        '''Reply to users using this command.'''
        categ = discord.utils.get(ctx.guild.categories, id=ctx.channel.category_id)
        if categ is not None and categ.name == 'Mod Mail':
            if 'User ID:' in ctx.channel.topic:
                ctx.message.content = msg
                await self.process_reply(ctx.message)

    @commands.command(name="customstatus", aliases=['status', 'presence'])
    @commands.has_permissions(administrator=True)
    async def _status(self, ctx, *, message):
        '''Set a custom playing status for the bot.'''
        if message == 'clear':
            return await self.change_presence(activity=None)
        await self.change_presence(activity=discord.Game(message))
        await ctx.send(f"Changed status to **{message}**")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def block(self, ctx, id=None):
        '''Block a user from using modmail.'''
        if id is None:
            if 'User ID:' in str(ctx.channel.topic):
                id = ctx.channel.topic.split('User ID: ')[1].strip()
            else:
                return await ctx.send('No User ID provided.')

        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        top_chan = categ.channels[0] #bot-info
        topic = str(top_chan.topic)
        topic += '\n' + id

        if id not in top_chan.topic:  
            await top_chan.edit(topic=topic)
            await ctx.send('User successfully blocked!')
        else:
            await ctx.send('User is already blocked.')

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def unblock(self, ctx, id=None):
        '''Unblocks a user from using modmail.'''
        if id is None:
            if 'User ID:' in str(ctx.channel.topic):
                id = ctx.channel.topic.split('User ID: ')[1].strip()
            else:
                return await ctx.send('No User ID provided.')

        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        top_chan = categ.channels[0] #bot-info
        topic = str(top_chan.topic)
        topic = topic.replace('\n'+id, '')

        if id in top_chan.topic:
            await top_chan.edit(topic=topic)
            await ctx.send('User successfully unblocked!')
        else:
            await ctx.send('User is not already blocked.')

    @commands.command(hidden=True, name='eval')
    async def _eval(self, ctx, *, body: str):
        """Evaluates python code"""
        allowed = [int(x) for x in os.getenv('OWNERS', '').split(',')]
        if ctx.author.id not in allowed: 
            return
        
        env = {
            'bot': self,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            'source': inspect.getsource
        }

        env.update(globals())

        body = self.cleanup_code(body)
        stdout = io.StringIO()
        err = out = None

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            err = await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')
            return await err.add_reaction('\u2049')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            err = await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        out = await ctx.send(f'```py\n{value}\n```')
                    except:
                        await ctx.send('```Result is too long to send.```')
            else:
                self._last_result = ret
                try:
                    out = await ctx.send(f'```py\n{value}{ret}\n```')
                except:
                    await ctx.send('```Result is too long to send.```')
        if out:
            await ctx.message.add_reaction('\u2705') #tick
        if err:
            await ctx.message.add_reaction('\u2049') #x
        else:
            await ctx.message.add_reaction('\u2705')

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')
        
if __name__ == '__main__':
    bot = Modmail()
    bot.run(bot.token)
