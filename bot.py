"""
MIT License

Copyright (c) 2017-2019 kyb3r

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
"""

__version__ = '2.11.0'

import asyncio
import uvloop
import textwrap
import datetime
import os
from types import SimpleNamespace

import discord
import aiohttp
from discord.enums import ActivityType
from discord.ext import commands
from discord.ext.commands.view import StringView
from motor.motor_asyncio import AsyncIOMotorClient

from colorama import init, Fore, Style
import emoji

from core.clients import Github, ModmailApiClient, SelfhostedClient
from core.thread import ThreadManager
from core.config import ConfigManager
from core.changelog import ChangeLog


init()

line = Fore.BLACK + Style.BRIGHT + '-------------------------' + Style.RESET_ALL


class ModmailBot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix=self.get_pre)
        self.version = __version__
        self.start_time = datetime.datetime.utcnow()
        self.threads = ThreadManager(self)
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.config = ConfigManager(self)
        self.selfhosted = bool(self.config.get('mongo_uri'))
        self._connected = asyncio.Event()
        if self.selfhosted:
            self.db = AsyncIOMotorClient(self.config.mongo_uri).modmail_bot
        self.modmail_api = SelfhostedClient(self) if self.selfhosted else ModmailApiClient(self)
        self.data_task = self.loop.create_task(self.data_loop())
        self.autoupdate_task = self.loop.create_task(self.autoupdate_loop())
        self._add_commands()

    def _add_commands(self):
        """Adds commands automatically"""
        self.remove_command('help')

        print(line + Fore.CYAN)
        print('┌┬┐┌─┐┌┬┐┌┬┐┌─┐┬┬',
              '││││ │ │││││├─┤││',
              '┴ ┴└─┘─┴┘┴ ┴┴ ┴┴┴─┘', sep='\n')
        print(f'v{__version__}')
        print('Authors: kyb3r, fourjr' + Style.RESET_ALL)
        print(line + Fore.CYAN)

        for file in os.listdir('cogs'):
            if not file.endswith('.py'):
                continue
            cog = f'cogs.{file[:-3]}'
            print(f'Loading {cog}')
            self.load_extension(cog)

    async def logout(self):
        await self.session.close()
        self.data_task.cancel()
        self.autoupdate_task.cancel()
        await super().logout()

    def run(self):
        try:
            super().run(self.token)
        finally:
            print(Fore.RED + ' - Shutting down bot' + Style.RESET_ALL)
        
    @property
    def log_channel(self):
        channel_id = self.config.get('log_channel_id')
        if channel_id is not None:
            return self.get_channel(int(channel_id))
        else:
            return self.main_category.channels[0]

    @property
    def snippets(self):
        return {k: v for k, v in self.config.get('snippets', {}).items() if v}

    @property
    def aliases(self):
        return {k: v for k, v in self.config.get('aliases', {}).items() if v}

    @property
    def token(self):
        return self.config.token

    @property
    def guild_id(self):
        return int(self.config.guild_id)

    @property
    def guild(self):
        '''The guild that the bot is serving (the server where users message it from)'''
        return discord.utils.get(self.guilds, id=self.guild_id)

    @property
    def modmail_guild(self):
        '''The guild that the bot is operating in (where the bot is creating threads)'''
        modmail_guild_id = self.config.get('modmail_guild_id')
        if not modmail_guild_id:
            return self.guild
        else:
            return discord.utils.get(self.guilds, id=int(modmail_guild_id))
    
    @property
    def using_multiple_server_setup(self):
        return self.modmail_guild != self.guild

    @property
    def main_category(self):
        category_id = self.config.get('main_category_id')
        if category_id is not None:
            return discord.utils.get(self.modmail_guild.categories, id=int(category_id))
        if self.modmail_guild:
            return discord.utils.get(self.modmail_guild.categories, name='Modmail')

    @property
    def blocked_users(self):
        return self.config.get('blocked', {})

    @property
    def prefix(self):
        return self.config.get('prefix', '?')
    
    @property
    def mod_color(self):
        color = self.config.get('mod_color')
        if not color:
            return discord.Color.green()
        try:
            color = int(color.strip('#'), base=16)
        except:
            print('Invalid mod_color provided')
            return discord.Color.green()
        else:
            return color

    @property
    def recipient_color(self):
        color = self.config.get('recipient_color')
        if not color:
            return discord.Color.gold()
        try:
            color = int(color.strip('#'), base=16)
        except:
            print('Invalid recipient_color provided')
            return discord.Color.gold()
        else:
            return color

    @staticmethod
    async def get_pre(bot, message):
        """Returns the prefix."""
        return [bot.prefix, f'<@{bot.user.id}> ', f'<@!{bot.user.id}> ']

    async def on_connect(self):
        print(line)
        print(Fore.CYAN, end='')
        if not self.selfhosted:
            print('MODE: Using the Modmail API')
            print(line)
            await self.validate_api_token()
            print(line)
        else:
            await self.validate_database_connection()
            print('Mode: Selfhosting logs.')
            print(line)
        print(Fore.CYAN + 'Connected to gateway.')
        
        await self.config.refresh()

        activity_type = self.config.get('activity_type')
        message = self.config.get('activity_message')

        if activity_type is not None and message:
            url = self.config.get('twitch_url', 'https://www.twitch.tv/discord-modmail/') if activity_type == ActivityType.streaming else None
            activity = discord.Activity(type=activity_type, name=message,
                                        url=url)
            await self.change_presence(activity=activity)
        
        self._connected.set()

    async def on_ready(self):
        """Bot startup, sets uptime."""

        await self._connected.wait()

        print(textwrap.dedent(f"""
        {line}
        {Fore.CYAN}Client ready.
        {line}
        {Fore.CYAN}Logged in as: {self.user}
        {Fore.CYAN}User ID: {self.user.id}
        {Fore.CYAN}Guild ID: {self.guild.id if self.guild else 0}
        {line}
        """).strip())

        if not self.guild:
            print(Fore.RED + Style.BRIGHT + 'WARNING - The GUILD_ID provided does not exist!' + Style.RESET_ALL)
        else:
            await self.threads.populate_cache()
        
        await self.config.wait_until_ready() # Wait until config cache is popluated with stuff from db

        closures = self.config.closures.copy()

        for recipient_id, items in closures.items():
            after = (datetime.datetime.fromisoformat(items['time']) -
                     datetime.datetime.utcnow()).total_seconds()
            if after < 0:
                after = 0
            recipient = self.get_user(int(recipient_id))

            thread = await self.threads.find(
                recipient=recipient)

            if not thread:
                # If the recipient is gone or channel is deleted
                self.config.closures.pop(str(recipient_id))
                await self.config.update()
                continue

            # TODO: Low priority,
            #  Retrieve messages/replies when bot is down, from history?
            self.loop.create_task(
                thread.close(
                    closer=self.get_user(items['closer_id']),
                    after=after,
                    silent=items['silent'],
                    delete_channel=items['delete_channel'],
                    message=items['message']
                )
            )


    async def process_modmail(self, message):
        """Processes messages sent to the bot."""

        ctx = SimpleNamespace(bot=self, guild=self.modmail_guild)
        converter = commands.EmojiConverter()

        blocked_emoji = self.config.get('blocked_emoji', '🚫')
        sent_emoji = self.config.get('sent_emoji', '✅')

        if blocked_emoji not in emoji.UNICODE_EMOJI:
            try:
                blocked_emoji = await converter.convert(ctx, blocked_emoji.strip(':'))
            except:
                pass

        if sent_emoji not in emoji.UNICODE_EMOJI:
            try:
                sent_emoji = await converter.convert(ctx, sent_emoji.strip(':'))
            except:
                pass

        reaction = blocked_emoji if str(message.author.id) in self.blocked_users else sent_emoji

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

    async def get_context(self, message, *, cls=commands.Context):
        """
        Returns the invocation context from the message.
        Supports getting the prefix from database as well as command aliases.
        """

        view = StringView(message.content)
        ctx = cls(prefix=None, view=view, bot=self, message=message)

        if self._skip_check(message.author.id, self.user.id):
            return ctx

        prefixes = [self.prefix, f'<@{bot.user.id}> ', f'<@!{bot.user.id}> ']

        invoked_prefix = discord.utils.find(view.skip_string, prefixes)
        if invoked_prefix is None:
            return ctx

        invoker = view.get_word().lower()

        # Check if there is any aliases being called.
        alias = self.config.get('aliases', {}).get(invoker)
        if alias is not None:
            ctx._alias_invoked = True
            _len = len(f'{invoked_prefix}{invoker}')
            ctx.view = view = StringView(f'{alias}{ctx.message.content[_len:]}')
            invoker = view.get_word()

        ctx.invoked_with = invoker
        ctx.prefix = self.prefix  # Sane prefix (No mentions)
        ctx.command = self.all_commands.get(invoker)
        
        if ctx.command is self.get_command('eval') and hasattr(ctx, '_alias_invoked'):
            # ctx.command.checks = None # Let anyone use the command.
            pass

        return ctx

    async def on_message(self, message):
        if message.type == discord.MessageType.pins_add and message.author == self.user:
            await message.delete()
        if message.author.bot:
            return
        if isinstance(message.channel, discord.DMChannel):
            return await self.process_modmail(message)

        prefix = self.prefix

        if message.content.startswith(prefix):
            cmd = message.content[len(prefix):].strip()
            if cmd in self.snippets:
                message.content = f'{prefix}reply {self.snippets[cmd]}'
    
        ctx = await self.get_context(message)
        if ctx.command:
            return await self.invoke(ctx)

        thread = await self.threads.find(channel=ctx.channel)

        if thread is not None:
            await self.modmail_api.append_log(message, type='internal')
    
    async def on_guild_channel_delete(self, channel):
        if channel.guild != self.modmail_guild:
            return 

        mod = None 
        audit_logs = self.modmail_guild.audit_logs()
        entry = await audit_logs.find(lambda e: e.target.id == channel.id)
        mod = entry.user

        if mod == self.user:
            return
        
        thread = await self.threads.find(channel=channel)
        if not thread:
            return
        
        await thread.close(closer=mod, silent=True, delete_channel=False)


    async def on_message_delete(self, message):
        """Support for deleting linked messages"""
        if message.embeds and not isinstance(message.channel, discord.DMChannel):
            message_id = str(message.embeds[0].author.url).split('/')[-1]
            if message_id.isdigit():
                thread = await self.threads.find(channel=message.channel)

                channel = thread.recipient.dm_channel

                async for msg in channel.history():
                    if msg.embeds and msg.embeds[0].author:
                        url = str(msg.embeds[0].author.url)
                        if message_id == url.split('/')[-1]:
                            return await msg.delete()

    async def on_message_edit(self, before, after):
        if before.author.bot:
            return
        if isinstance(before.channel, discord.DMChannel):
            thread = await self.threads.find(recipient=before.author)
            async for msg in thread.channel.history():
                if msg.embeds:
                    embed = msg.embeds[0]
                    matches = str(embed.author.url).split('/')
                    if matches and matches[-1] == str(before.id):
                        embed.description = after.content
                        await msg.edit(embed=embed)
                        await self.modmail_api.edit_message(str(after.id), after.content)
                        break

    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.UserInputError)):
            await ctx.invoke(self.get_command('help'), command=str(ctx.command))
        else:
            raise error

    def overwrites(self, ctx):
        """Permision overwrites for the guild."""
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        for role in ctx.guild.roles:
            if role.permissions.manage_guild:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True)

        return overwrites

    async def validate_api_token(self):
        try:
            self.config.modmail_api_token
        except KeyError:
            print(Fore.RED + Style.BRIGHT, end='')
            print('MODMAIL_API_TOKEN not found.')
            print('Set a config variable called MODMAIL_API_TOKEN with a token from https://dashboard.modmail.tk')
            print('If you want to selfhost logs, input a MONGO_URI config variable.')
            print('A modmail api token is not needed if you are selfhosting logs.')
            valid = False
        else:
            valid = await self.modmail_api.validate_token()
            if not valid:
                print(Fore.RED, end='')
                print('Invalid MODMAIL_API_TOKEN - get one from https://dashboard.modmail.tk')
        finally:
            if not valid:
                await self.logout()
            else:
                username = (await self.modmail_api.get_user_info())['user']['username']
                print(Style.RESET_ALL + Fore.CYAN + 'Validated token.' )
                print(f'GitHub user: {username}' + Style.RESET_ALL)
    
    async def validate_database_connection(self):
        try:
            doc = await self.db.command('buildinfo')
        except Exception as e:
            valid = False
            print(Fore.RED, end='')
            print('Something went wrong while connecting to the database.')
            print(type(e).__name__, e, sep=': ')
        else:
            valid = True
            print(Style.RESET_ALL + Fore.CYAN + 'Successfully connected to the database.' )
        finally:
            if not valid:
                await self.logout()

    async def data_loop(self):
        await self.wait_until_ready()
        self.owner = (await self.application_info()).owner

        while True:
            data = {
                "owner_name": str(self.owner),
                "owner_id": self.owner.id,
                "bot_id": self.user.id,
                "bot_name": str(self.user),
                "avatar_url": self.user.avatar_url,
                "guild_id": self.guild_id,
                "guild_name": self.guild.name,
                "member_count": len(self.guild.members),
                "uptime": (datetime.datetime.utcnow() - self.start_time).total_seconds(),
                "latency": f'{self.ws.latency * 1000:.4f}',
                "version": self.version,
                "selfhosted": self.selfhosted,
                "last_updated": str(datetime.datetime.utcnow())
            }

            await self.modmail_api.post_metadata(data)

            await asyncio.sleep(3600)

    async def autoupdate_loop(self):
        await self.wait_until_ready()

        if self.config.get('disable_autoupdates'):
            print('Autoupdates disabled.')
            print(line)
            return 

        if self.selfhosted and not self.config.get('github_access_token'):
            print('Github access token not found.')
            print('Autoupdates disabled.')
            print(line)
            return 

        while True:
            metadata = await self.modmail_api.get_metadata()

            if metadata['latest_version'] != self.version:
                data = await self.modmail_api.update_repository()
                

                em = discord.Embed(color=discord.Color.green())

                commit_data = data['data']
                user = data['user']
                em.set_author(name=user['username'] + ' - Updating Bot', icon_url=user['avatar_url'], url=user['url'])
                em.set_footer(text=f"Updating modmail v{self.version} -> v{metadata['latest_version']}")

                changelog = await ChangeLog.from_repo(self)
                latest = changelog.latest_version
                em.description = latest.description
                for name, value in latest.fields.items():
                    em.add_field(name=name, value=value)

                if commit_data:
                    message = commit_data['commit']['message']
                    html_url = commit_data["html_url"]
                    short_sha = commit_data['sha'][:6]
                    em.add_field(name='Merge Commit', value=f"[`{short_sha}`]({html_url}) {message} - {user['username']}")
                    print('Updating bot.')
                    channel = self.log_channel
                    await channel.send(embed=em)

            await asyncio.sleep(3600)

    async def get_latest_updates(self, limit=3):
        latest_commits = ''

        async for commit in Github(self).get_latest_commits(limit=limit):

            short_sha = commit['sha'][:6]
            html_url = commit['html_url']
            message = commit['commit']['message'].splitlines()[0]

            latest_commits += f'[`{short_sha}`]({html_url}) {message}\n'

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
    uvloop.install()
    bot = ModmailBot()
    bot.run()
