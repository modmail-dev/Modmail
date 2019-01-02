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

from utils.paginator import PaginatorSession
from utils.api import Github, ModmailApiClient
from utils.modmail import ThreadManager, Thread

line = Fore.RED + Style.BRIGHT + '-------------------------' + Style.RESET_ALL

class Modmail(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix=self.get_pre)
        self.start_time = datetime.datetime.utcnow()
        self.threads = ThreadManager(self) 
        self.loop.create_task(self.data_loop())
        self._add_commands()

    def _add_commands(self):
        '''Adds commands automatically'''
        self.remove_command('help')
        print(line + Fore.YELLOW)
        print('┌┬┐┌─┐┌┬┐┌┬┐┌─┐┬┬',
              '││││ │ │││││├─┤││',
              '┴ ┴└─┘─┴┘┴ ┴┴ ┴┴┴─┘', sep='\n')
        print(f'v{__version__}')
        print('Author: kyb3r' + Style.RESET_ALL)
        for attr in dir(self):
            cmd = getattr(self, attr)
            if isinstance(cmd, commands.Command):
                self.add_command(cmd)

    @property
    def config(self):
        try:
            with open('config.json') as f:
                config = json.load(f)
        except FileNotFoundError:
            print('config.json not found, falling back to env vars.')
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
        '''Returns your token wherever it is'''
        return self.config.get('TOKEN')

    @property
    def guild_id(self):
        return int(self.config.get('GUILD_ID'))
    
    @property
    def guild(self):
        g = discord.utils.get(self.guilds, id=self.guild_id)
        return g

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
    
    def owner_only():
        async def predicate(ctx):
            allowed = [int(x) for x in ctx.bot.config.get('OWNERS', '0').split(',')]
            return ctx.author.id in allowed
        return commands.check(predicate)
    
    def trigger_typing(func):
        @functools.wraps(func)
        async def wrapper(self, ctx, *args, **kwargs):
            await ctx.trigger_typing()
            return await func(self, ctx, *args, **kwargs)
        return wrapper
    
    def modmail_api_token_required(func):
        @functools.wraps(func)
        async def wrapper(self, ctx, *args, **kwargs):
            if self.config.get('MODMAIL_API_TOKEN'):
                return await func(self, ctx, *args, **kwargs)
            em = discord.Embed(
                color=discord.Color.red(),
                title='Unauthorized',
                description='You can only use this command if you have a configured `MODMAIL_API_TOKEN`. Get your token from https://dashboard.modmail.tk'
                )
            await ctx.send(embed=em)
        return wrapper 

    async def on_connect(self):
        print(line)
        print(Fore.YELLOW + 'Connected to gateway.')
        
        self.session = aiohttp.ClientSession()
        self.modmail_api = ModmailApiClient(self) 
        status = os.getenv('STATUS') or self.config.get('STATUS')
        if status:
            await self.change_presence(activity=discord.Game(status))

    async def on_ready(self):
        '''Bot startup, sets uptime.'''
        print(textwrap.dedent(f'''
        {line}
        {Fore.YELLOW}Client ready.
        {line}
        {Fore.YELLOW}Logged in as: {self.user}
        {Fore.YELLOW}User ID: {self.user.id}
        {Fore.YELLOW}Guild ID: {self.guild.id if self.guild else 0}
        {line}
        ''').strip())
        
        await self.threads.populate_cache()

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
            prefix = self.config.get('PREFIX', 'm.')
            em = discord.Embed(color=discord.Color.green())
            em.title = f'`{prefix}{ctx.command.signature}`'
            em.description = ctx.command.help
            await ctx.send(embed=em)
        else:
            raise error

    def overwrites(self, ctx):
        '''Permision overwrites for the guild.'''
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }

        for role in self.guess_modroles(ctx):
            overwrites[role] = discord.PermissionOverwrite(read_messages=True)

        return overwrites

    def help_embed(self, prefix):
        em = discord.Embed(color=0x00FFFF)
        em.set_author(name='Mod Mail - Help', icon_url=self.user.avatar_url)
        em.description = 'Here is a list of commands for the bot.'

        cmds = f'`{prefix}setup` - Sets up the categories that will be used by the bot.\n' \
               f'`{prefix}about` - Shows general information about the bot.\n' \
               f'`{prefix}contact` - Allows a moderator to initiate a thread with a given recipient.\n' \
               f'`{prefix}reply` - Sends a message to the current thread\'s recipient.\n' \
               f'`{prefix}edit` - Edit a message sent by the reply command.\n' \
               f'`{prefix}close` - Closes the current thread and deletes the channel.\n' \
               f'`{prefix}archive` - Closes the thread and moves the channel to archive category.\n' \
               f'`{prefix}block` - Blocks a user from using modmail.\n' \
               f'`{prefix}blocked` - Shows a list of currently blocked users.\n' \
               f'`{prefix}unblock` - Unblocks a user from using modmail.\n' \
               f'`{prefix}snippets` - See a list of snippets that are currently configured.\n' \
               f'`{prefix}customstatus` - Sets the Bot status to whatever you want.\n' \
               f'`{prefix}disable` - Closes all threads and disables modmail for the server.\n' \
               f'`{prefix}update` - Checks for a new version and updates the bot.\n' 

        warn = 'This bot saves no data and utilises channel topics for tracking and relaying messages.' \
               ' Therefore do not manually delete the category or channels as it will break the system. ' \
               'Modifying the channel topic will also break the system. Dont break the system buddy.'

        snippets = 'Snippets are shortcuts for predefined messages that you can send.' \
                   ' You can add snippets by adding config variables in the form **`SNIPPET_{NAME}`**' \
                   ' and setting the value to what you want the message to be. You can now use the snippet by' \
                   f' typing the command `{prefix}name` in the thread you want to reply to.'

        mention = 'If you want the bot to mention a specific role instead of @here,' \
                  ' you need to set a config variable **`MENTION`** and set the value ' \
                  'to the *mention* of the role or user you want mentioned. To get the ' \
                  'mention of a role or user, type `\@role` in chat and you will see ' \
                  'something like `<@&515651147516608512>` use this string as ' \
                  'the value for the config variable.'

        em.add_field(name='Commands', value=cmds)
        em.add_field(name='Snippets', value=snippets)
        em.add_field(name='Custom Mentions', value=mention)
        em.add_field(name='Warning', value=warn)
        em.add_field(name='Github', value='https://github.com/kyb3r/modmail')
        em.set_footer(text=f'modmail v{__version__} • A star on the repository is appreciated.')

        return em
    
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

    @commands.command()
    @trigger_typing
    async def help(self, ctx):
        '''Shows the help message'''
        prefix = self.config.get('PREFIX', 'm.')

        em1 = self.help_embed(prefix)
        em2 = deepcopy(em1)
        em1.set_footer(text=f'modmail v{__version__}')
        em2.description = None
        em2.remove_field(0)
        em1._fields = em1._fields[0:1]

        session = PaginatorSession(ctx, em1, em2)
        await session.run()
    
    @commands.command()
    @trigger_typing
    async def about(self, ctx):
        '''Shows information about the bot.'''
        em = discord.Embed(color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
        em.set_author(name='Mod Mail - Information', icon_url=self.user.avatar_url)
        em.set_thumbnail(url=self.user.avatar_url)

        em.description = 'This is an open source discord bot made by kyb3r and '\
                         'improved upon suggestions by the users! This bot serves as a means for members to '\
                         'easily communicate with server leadership in an organised manner.'

        try:
            async with self.session.get('https://api.modmail.tk/metadata') as resp:
                meta = await resp.json()
        except:
            meta = None

        em.add_field(name='Uptime', value=self.uptime)
        if meta:
            em.add_field(name='Instances', value=meta['instances'])
        else:
            em.add_field(name='Latency', value=f'{self.latency*1000:.2f} ms')
        

        em.add_field(name='Version', value=f'[`{__version__}`](https://github.com/kyb3r/modmail/blob/master/bot.py#L25)')
        em.add_field(name='Author', value='[`kyb3r`](https://github.com/kyb3r)')

        em.add_field(name='Latest Updates', value=await self.get_latest_updates())
        
        footer = f'Bot ID: {self.user.id}'
        
        if meta:
            if __version__ != meta['latest_version']:
                footer = f"A newer version is available v{meta['latest_version']}"
            else:
                footer = 'You are up to date with the latest version.'
        
        em.add_field(name='Github', value='https://github.com/kyb3r/modmail', inline=False)

        em.set_footer(text=footer)

        await ctx.send(embed=em)
    
    @commands.command()
    @owner_only()
    @modmail_api_token_required
    @trigger_typing
    async def github(self, ctx):
        if ctx.invoked_subcommand:
            return

        data = await self.modmail_api.get_user_info()
        print(data)

        prefix = self.config.get('PREFIX', 'm.')

        em = discord.Embed(title='Github')

        user = data['user']
        em.color = discord.Color.green()
        em.description = f"Current user."
        em.set_author(name=user['username'], icon_url=user['avatar_url'], url=user['url'])
        em.set_thumbnail(url=user['avatar_url'])
        await ctx.send(embed=em)

    
    @commands.command()
    @owner_only()
    @modmail_api_token_required
    @trigger_typing
    async def update(self, ctx):
        '''Updates the bot, this only works with heroku users.'''
        metadata = await self.modmail_api.get_metadata()

        em = discord.Embed(
                title='Already up to date',
                description=f'The latest version is [`{__version__}`](https://github.com/kyb3r/modmail/blob/master/bot.py#L25)',
                color=discord.Color.green()
        )

        if metadata['latest_version'] == __version__:
            data = await self.modmail_api.get_user_info()
            if not data['error']:
                user = data['user']
                em.set_author(name=user['username'], icon_url=user['avatar_url'], url=user['url'])
        else:
            data = await self.modmail_api.update_repository()

            commit_data = data['data']
            user = data['user']
            em.title = 'Success'
            em.set_author(name=user['username'], icon_url=user['avatar_url'], url=user['url'])
            em.set_footer(text=f"Updating modmail v{__version__} -> v{metadata['latest_version']}")  

            if commit_data:
                em.description = 'Bot successfully updated, the bot will restart momentarily'
                message = commit_data['commit']['message']
                html_url = commit_data["html_url"]
                short_sha = commit_data['sha'][:6]
                em.add_field(name='Merge Commit', value=f"[`{short_sha}`]({html_url}) {message} - {user['username']}")
            else:
                em.description = 'Already up to date with master repository.'

        em.add_field(name='Latest Commit', value=await self.get_latest_updates(limit=1), inline=False)

        await ctx.send(embed=em)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        '''Sets up a server for modmail'''
        if self.main_category:
            return await ctx.send('This server is already set up.')

        categ = await ctx.guild.create_category(
            name='Mod Mail', 
            overwrites=self.overwrites(ctx, modrole=modrole)
            )

        await categ.edit(position=0)

        c = await ctx.guild.create_text_channel(name='bot-info', category=categ)
        
        await c.edit(topic='Manually add user id\'s to block users.\n\n'
                           'Blocked\n-------\n\n')

        await c.send(embed=self.help_embed(ctx.prefix))

        await ctx.guild.create_text_channel(name='thread-logs', category=categ)

        await ctx.send('Successfully set up server.')
    
    @commands.command(name='snippets')
    @commands.has_permissions(manage_messages=True)
    async def _snippets(self, ctx):
        '''Returns a list of snippets that are currently set.'''
        embeds = []

        em = discord.Embed(color=discord.Color.green())
        em.set_author(name='Snippets', icon_url=ctx.guild.icon_url)

        embeds.append(em)

        em.description = 'Here is a list of snippets that are currently configured.'

        if not self.snippets:
            em.color = discord.Color.red()
            em.description = 'You dont have any snippets at the moment.'
        
        for name, value in self.snippets.items():
            if len(em.fields) == 5:
                em = discord.Embed(color=discord.Color.green(), description=em.description)
                em.set_author(name='Snippets', icon_url=ctx.guild.icon_url)
                embeds.append(em)
            em.add_field(name=name, value=value, inline=False)
        
        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @commands.command(name='close')
    @commands.has_permissions(manage_channels=True)
    async def _close(self, ctx):
        '''Close the current thread.'''
        
        thread = await self.threads.find(channel=ctx.channel)
        if not thread:
            return await ctx.send('This is not a modmail thread.')

        await thread.close()

        em = discord.Embed(title='Thread Closed')
        em.description = f'{ctx.author.mention} has closed this modmail thread.'
        em.color = discord.Color.red()

        try:
            await thread.recipient.send(embed=em)
        except:
            pass

        # Logging
        categ = self.main_category
        log_channel = categ.channels[1]

        log_data = await self.modmail_api.post_log(ctx.channel.id, {
            'open': False, 'closed_at': str(datetime.datetime.utcnow()), 'closer': {
                'id': str(ctx.author.id),
                'name': ctx.author.name,
                'discriminator': ctx.author.discriminator,
                'avatar_url': ctx.author.avatar_url,
                'mod': True
            }
        })

        log_url = f"https://logs.modmail.tk/{log_data['user_id']}/{log_data['key']}"

        user = thread.recipient.mention if thread.recipient else f'`{thread.id}`'

        desc = f"[`{log_data['key']}`]({log_url}) {ctx.author.mention} closed a thread with {user}"
        em = discord.Embed(description=desc, color=em.color)
        em.set_author(name='Thread closed', url=log_url)
        await log_channel.send(embed=em)

    @commands.command()
    async def nsfw(self, ctx):
        if ctx.channel.category and ctx.channel.category.name == 'Mod Mail':
            await ctx.edit(nsfw=True)
        em = discord.Embed(description=desc, color=discord.Color.green())
        em.set_author(name='Thread closed', url=log_url)
        await ctx.send('Done')
        
    @commands.command()
    @trigger_typing
    @commands.has_permissions(administrator=True)
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

    def format_info(self, user, creator, log_url, log_count=None):
        '''Get information about a member of a server
        supports users from the guild or not.'''
        server = self.guild
        member = self.guild.get_member(user.id)
        avi = user.avatar_url
        time = datetime.datetime.utcnow()
        desc = f'{creator.mention} has created a thread with {user.mention}' if creator else f'{user.mention} has started a thread.'
        key = log_url.split('/')[-1]
        desc = f'{desc} [`{key}`]({log_url})'
        color = discord.Color.blurple()

        if member:
            roles = sorted(member.roles, key=lambda c: c.position)
            rolenames = ' '.join([r.mention for r in roles if r.name != "@everyone"])
            # member_number = sorted(server.members, key=lambda m: m.joined_at).index(member) + 1
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
        em.set_author(name=str(user), icon_url=avi)
        em.set_thumbnail(url=avi)

        if member:
            if log_count:
                em.add_field(name='Past logs', value=f'{log_count}')
            joined = str((time - member.joined_at).days)
            em.add_field(name='Joined', value=joined + days(joined))
            # em.add_field(name='Member No.',value=str(member_number),inline = True)
            em.add_field(name='Nickname', value=member.nick, inline=True)
            if rolenames:
                em.add_field(name='Roles', value=rolenames, inline=False)
        else:
            em.set_footer(text=footer+' | Note: this member is not part of this server.')

        return em

    def format_channel_name(self, author):
        name = author.name.lower()
        allowed = string.ascii_letters + string.digits + '-'
        new_name = ''.join(l for l in name if l in allowed) or 'null'
        new_name += f'-{author.discriminator}'
        while new_name in [c.name for c in self.guild.text_channels]:
            new_name += '-x' # two channels with same name
        return new_name

    @property
    def blocked_em(self):
        em = discord.Embed(title='Message not sent!', color=discord.Color.red())
        em.description = 'You have been blocked from using modmail.'
        return em

    async def process_modmail(self, message):
        '''Processes messages sent to the bot.'''

        reaction = '🚫' if message.author.id in self.blocked_users else '✅'

        try:
            await message.add_reaction(reaction)
        except:
            pass

        if str(message.author.id) in self.blocked_users:
            await message.author.send(embed=self.blocked_em)
        else:
            thread = await self.threads.find_or_create(message.author)
            await thread.send(message)
    
    @commands.command()
    @trigger_typing
    async def logs(self, ctx, *, member: discord.Member=None):

        if not member:
            thread = await self.threads.find(channel=ctx.channel)
            if not thread:
                raise commands.UserInputError

        user = member or thread.recipient

        logs = await self.modmail_api.get_user_logs(user.id)

        if not any(not e['open'] for e in logs):
            return await ctx.send('This user has no previous logs.')

        em = discord.Embed(color=discord.Color.green())
        em.set_author(name='Previous Logs', icon_url=user.avatar_url)

        embeds = [em]

        current_day = dateutil.parser.parse(logs[0]['created_at']).strftime(r'%d %b %Y')

        fmt = ''

        for index, entry in enumerate(logs):
            if len(embeds[-1].fields) == 3:
                em = discord.Embed(color=discord.Color.green())
                em.set_author(name='Previous Logs', icon_url=user.avatar_url)
                embeds.append(em)

            date = dateutil.parser.parse(entry['created_at'])
            new_day = date.strftime(r'%d %b %Y')
            
            key = entry['key']
            user_id = entry['user_id']
            log_url = f"https://logs.modmail.tk/{user_id}/{key}"
            
            if not entry['open']:  # only list closed threads
                fmt += f"[`{key}`]({log_url})\n"

                if current_day != new_day or index == len(logs) - 2:
                    embeds[-1].add_field(name=current_day, value=fmt)
                    current_day = new_day
                    fmt = ''

        
        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @commands.command()
    @trigger_typing
    async def reply(self, ctx, *, msg=''):
        '''Reply to users using this command.
        
        Supports attachments and images as well as automatically embedding image_urls.
        '''
        ctx.message.content = msg
        thread = await self.threads.find(channel=ctx.channel)
        if thread and thread.channel.category.name == 'Mod Mail':
            await thread.reply(ctx.message)
    
    @commands.command()
    async def edit(self, ctx, message_id: int, *, new_message):
        '''Edit a message that was sent using the reply command.
        
        `<message_id>` is the id shown in the footer of thread messages.
        `<new_message>` is the new message that will be edited in.
        '''
        thread = self.threads.find(channel=ctx.channel)
        if thread and thread.category.name == 'Mod Mail':
            await thread.edit_message(message_id, new_message)
            
    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def contact(self, ctx, *, user: discord.Member):
        '''Create a thread with a specified member.'''

        exists = await self.threads.find(recipient=user)
        if exists:
            return await ctx.send('Thread already exists.')
        else:
            thread = await self.threads.create(user, creator=ctx.author)
        
        em = discord.Embed(
            title='Created thread',
            description=f'Thread started in {thread.channel.mention} for {user.mention}',
            color=discord.Color.green()
            )

        await ctx.send(embed=em)

    @commands.command(name="customstatus", aliases=['status', 'presence'])
    @commands.has_permissions(administrator=True)
    async def _status(self, ctx, *, message):
        '''Set a custom playing status for the bot.'''
        if message == 'clear':
            return await self.change_presence(activity=None)
        await self.change_presence(activity=discord.Game(message))
        em = discord.Embed(title='Status Changed')
        em.description = message
        em.color = discord.Color.green()
        em.set_footer(text='Note: this change is temporary.')
        await ctx.send(embed=em)
    
    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def blocked(self, ctx):
        '''Returns a list of blocked users'''
        em = discord.Embed(title='Blocked Users', color=discord.Color.green())
        em.description = ''

        users = []
        not_reachable = []

        for id in self.blocked_users:
            user = self.get_user(id)
            if user:
                users.append(user)
            else:
                not_reachable.append(id)
        
        em.description = 'Here is a list of blocked users.'
        
        if users:
            em.add_field(name='Currently Known', value=' '.join(u.mention for u in users))
        if not_reachable:
            em.add_field(name='Unknown', value='\n'.join(f'`{i}`' for i in not_reachable), inline=False)
        
        if not users and not not_reachable:
            em.description = 'Currently there are no blocked users'

        await ctx.send(embed=em)
        
    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def block(self, ctx, id=None):
        '''Block a user from using modmail.'''

        if id is None:
            thread = await self.threads.find(channel=ctx.channel)
            if thread:
                id = thread.recipient.id
            else:
                raise commands.UserInputError

        categ = self.main_category
        top_chan = categ.channels[0] #bot-info
        topic = str(top_chan.topic)
        topic += '\n' + id

        user = self.get_user(int(id))
        mention = user.mention if user else f'`{id}`'

        em = discord.Embed()
        em.color = discord.Color.green()

        if id not in top_chan.topic:  
            await top_chan.edit(topic=topic)

            em.title = 'Success'
            em.description = f'{mention} is now blocked'

            await ctx.send(embed=em)
        else:
            em.title = 'Error'
            em.description = f'{mention} is already blocked'
            em.color = discord.Color.red()

            await ctx.send(embed=em)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def unblock(self, ctx, id=None):
        '''Unblocks a user from using modmail.'''
        if id is None:
            thread = await self.threads.find(channel=ctx.channel)
            if thread: 
                id = thread.recipient.id
            else:
                raise commands.UserInputError

        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        top_chan = categ.channels[0] #bot-info
        topic = str(top_chan.topic)
        topic = topic.replace('\n'+id, '')

        user = self.get_user(int(id))
        mention = user.mention if user else f'`{id}`'

        em = discord.Embed()
        em.color = discord.Color.green()

        if id in top_chan.topic:  
            await top_chan.edit(topic=topic)

            em.title = 'Success'
            em.description = f'{mention} is no longer blocked'

            await ctx.send(embed=em)
        else:
            em.title = 'Error'
            em.description = f'{mention} is not already blocked'
            em.color = discord.Color.red()

            await ctx.send(embed=em)

    @commands.command(hidden=True, name='eval')
    @owner_only()
    async def _eval(self, ctx, *, body: str):
        """Evaluates python code"""
        
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
