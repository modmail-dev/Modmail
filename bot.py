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

__version__ = '2.13.9'

import asyncio
import logging
import os
import re
import sys

from datetime import datetime
from types import SimpleNamespace

import discord
from discord.ext import commands
from discord.ext.commands.view import StringView

from aiohttp import ClientSession
from colorama import init, Fore, Style
from emoji import UNICODE_EMOJI
from motor.motor_asyncio import AsyncIOMotorClient

from core.changelog import Changelog
from core.clients import ModmailApiClient, SelfHostedClient
from core.clients import PluginDatabaseClient
from core.config import ConfigManager
from core.utils import info, error
from core.models import Bot
from core.thread import ThreadManager


init()

logger = logging.getLogger('Modmail')
logger.setLevel(logging.INFO)

ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(filename)s - %(levelname)s: %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


class FileFormatter(logging.Formatter):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')

    def format(self, record):
        record.msg = self.ansi_escape.sub('', record.msg)
        return super().format(record)


temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
if not os.path.exists(temp_dir):
    os.mkdir(temp_dir)

ch_debug = logging.FileHandler(
    os.path.join(temp_dir, 'logs.log'),
    mode='a+'
)

ch_debug.setLevel(logging.DEBUG)
formatter_debug = FileFormatter('%(asctime)s %(filename)s - '
                                '%(levelname)s: %(message)s',
                                datefmt='%Y-%m-%d %H:%M:%S')
ch_debug.setFormatter(formatter_debug)
logger.addHandler(ch_debug)

LINE = Fore.BLACK + Style.BRIGHT + '-------------------------' + \
       Style.RESET_ALL


class ModmailBot(Bot):

    def __init__(self):
        super().__init__(command_prefix=None)  # implemented in `get_prefix`
        self._threads = None
        self._session = None
        self._config = None
        self._db = None

        self._configure_logging()

        if self.self_hosted:
            self._db = AsyncIOMotorClient(self.config.mongo_uri).modmail_bot
            self._api = SelfHostedClient(self)
        else:
            self._api = ModmailApiClient(self)
        self.plugin_db = PluginDatabaseClient(self)

        self.data_task = self.loop.create_task(self.data_loop())
        self.autoupdate_task = self.loop.create_task(self.autoupdate_loop())
        self._load_extensions()
        self.owner = None

    def _configure_logging(self):
        level_text = self.config.log_level.upper()
        logging_levels = {
            'CRITICAL': logging.CRITICAL,
            'ERROR': logging.ERROR,
            'WARNING': logging.WARNING,
            'INFO': logging.INFO,
            'DEBUG': logging.DEBUG,
        }

        log_level = logging_levels.get(level_text)
        logger.info(LINE)
        if log_level is not None:
            logger.setLevel(log_level)
            ch.setLevel(log_level)
            logger.info(info('Logging level: ' + level_text))
        else:
            logger.info(error('Invalid logging level set. '))
            logger.info(info('Using default logging level: INFO'))

    @property
    def version(self):
        return __version__

    @property
    def db(self):
        return self._db

    @property
    def self_hosted(self):
        return bool(self.config.get('mongo_uri', ''))

    @property
    def api(self):
        return self._api

    @property
    def config(self):
        if self._config is None:
            self._config = ConfigManager(self)
        return self._config

    @property
    def session(self):
        if self._session is None:
            self._session = ClientSession(loop=self.loop)
        return self._session

    @property
    def threads(self):
        if self._threads is None:
            self._threads = ThreadManager(self)
        return self._threads

    async def get_prefix(self, message=None):
        return [self.prefix, f'<@{self.user.id}> ', f'<@!{self.user.id}> ']

    def _load_extensions(self):
        """Adds commands automatically"""
        self.remove_command('help')

        logger.info(LINE)
        logger.info(info('┌┬┐┌─┐┌┬┐┌┬┐┌─┐┬┬'))
        logger.info(info('││││ │ │││││├─┤││'))
        logger.info(info('┴ ┴└─┘─┴┘┴ ┴┴ ┴┴┴─┘'))
        logger.info(info(f'v{__version__}'))
        logger.info(info('Authors: kyb3r, fourjr, Taaku18'))
        logger.info(LINE)

        for file in os.listdir('cogs'):
            if not file.endswith('.py'):
                continue
            cog = f'cogs.{file[:-3]}'
            logger.info(info(f'Loading {cog}'))
            try:
                self.load_extension(cog)
            except Exception:
                logger.exception(error(f'Failed to load {cog}'))

    async def is_owner(self, user):
        allowed = {int(x) for x in
                   str(self.config.get('owners', '0')).split(',')}
        return user.id in allowed

    def run(self, *args, **kwargs):
        try:
            self.loop.run_until_complete(self.start(self.token))
        except discord.LoginFailure:
            logger.critical(error('Invalid token'))
        except KeyboardInterrupt:
            pass
        except Exception:
            logger.critical(error('Fatal exception'), exc_info=True)
        finally:
            try:
                self.data_task.cancel()
                self.loop.run_until_complete(self.data_task)
            except asyncio.CancelledError:
                logger.debug('data_task has been cancelled')

            try:
                self.autoupdate_task.cancel()
                self.loop.run_until_complete(self.autoupdate_task)
            except asyncio.CancelledError:
                logger.debug('autoupdate_task has been cancelled')

            self.loop.run_until_complete(self.logout())
            for task in asyncio.Task.all_tasks():
                task.cancel()
            try:
                self.loop.run_until_complete(
                    asyncio.gather(*asyncio.Task.all_tasks())
                )
            except asyncio.CancelledError:
                logger.debug('All pending tasks has been cancelled')
            finally:
                self.loop.run_until_complete(self.session.close())
                self.loop.close()
                logger.info(error(' - Shutting down bot - '))

    @property
    def log_channel(self):
        channel_id = self.config.get('log_channel_id')
        if channel_id is not None:
            return self.get_channel(int(channel_id))
        if self.main_category is not None:
            return self.main_category.channels[0]
        return None

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
        """
        The guild that the bot is serving
        (the server where users message it from)
        """
        return discord.utils.get(self.guilds, id=self.guild_id)

    @property
    def modmail_guild(self):
        """
        The guild that the bot is operating in
        (where the bot is creating threads)
        """
        modmail_guild_id = self.config.get('modmail_guild_id')
        if not modmail_guild_id:
            return self.guild
        return discord.utils.get(self.guilds, id=int(modmail_guild_id))

    @property
    def using_multiple_server_setup(self):
        return self.modmail_guild != self.guild

    @property
    def main_category(self):
        category_id = self.config.get('main_category_id')
        if category_id is not None:
            return discord.utils.get(self.modmail_guild.categories,
                                     id=int(category_id))

        if self.modmail_guild:
            return discord.utils.get(self.modmail_guild.categories,
                                     name='Modmail')
        return None

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
            color = int(color.lstrip('#'), base=16)
        except ValueError:
            logger.error(error('Invalid mod_color provided'))
            return discord.Color.green()
        else:
            return color

    @property
    def recipient_color(self):
        color = self.config.get('recipient_color')
        if not color:
            return discord.Color.gold()
        try:
            color = int(color.lstrip('#'), base=16)
        except ValueError:
            logger.error(error('Invalid recipient_color provided'))
            return discord.Color.gold()
        else:
            return color

    @property
    def main_color(self):
        color = self.config.get('main_color')
        if not color:
            return discord.Color.blurple()
        try:
            color = int(color.lstrip('#'), base=16)
        except ValueError:
            logger.error(error('Invalid main_color provided'))
            return discord.Color.blurple()
        else:
            return color

    async def on_connect(self):
        logger.info(LINE)
        if not self.self_hosted:
            logger.info(info('MODE: Using the Modmail API'))
            logger.info(LINE)
            await self.validate_api_token()
            logger.info(LINE)
        else:
            logger.info(info('Mode: Self-hosting logs.'))
            await self.validate_database_connection()
            logger.info(LINE)
        logger.info(info('Connected to gateway.'))

        await self.config.refresh()
        if self.db:
            await self.setup_indexes()
        self._connected.set()

    async def setup_indexes(self):
        """Setup text indexes so we can use the $search operator"""
        coll = self.db.logs
        index_name = 'messages.content_text_messages.author.name_text'

        index_info = await coll.index_information()

        # Backwards compatibility
        old_index = 'messages.content_text'
        if old_index in index_info:
            logger.info(info(f'Dropping old index: {old_index}'))
            await coll.drop_index(old_index)

        if index_name not in index_info:
            logger.info(info('Creating "text" index for logs collection.'))
            logger.info(info('Name: ' + index_name))
            await coll.create_index([
                ('messages.content', 'text'),
                ('messages.author.name', 'text')
            ])

    async def on_ready(self):
        """Bot startup, sets uptime."""
        await self._connected.wait()
        logger.info(LINE)
        logger.info(info('Client ready.'))
        logger.info(LINE)
        logger.info(info(f'Logged in as: {self.user}'))
        logger.info(info(f'User ID: {self.user.id}'))
        logger.info(info(f'Guild ID: {self.guild.id if self.guild else 0}'))
        logger.info(LINE)

        if not self.guild:
            logger.error(error('WARNING - The GUILD_ID '
                               'provided does not exist!'))
        else:
            await self.threads.populate_cache()

        # Wait until config cache is populated with stuff from db
        await self.config.wait_until_ready()

        # closures
        closures = self.config.closures.copy()
        logger.info(info(f'There are {len(closures)} thread(s) '
                         'pending to be closed.'))

        for recipient_id, items in closures.items():
            after = (datetime.fromisoformat(items['time']) -
                     datetime.utcnow()).total_seconds()
            if after < 0:
                after = 0
            recipient = self.get_user(int(recipient_id))

            thread = await self.threads.find(recipient=recipient)

            if not thread:
                # If the recipient is gone or channel is deleted
                self.config.closures.pop(str(recipient_id))
                await self.config.update()
                continue

            # TODO: Low priority,
            #  Retrieve messages/replies when bot is down, from history?
            await thread.close(
                closer=self.get_user(items['closer_id']),
                after=after,
                silent=items['silent'],
                delete_channel=items['delete_channel'],
                message=items['message']
            )
        logger.info(LINE)

    async def process_modmail(self, message):
        """Processes messages sent to the bot."""

        ctx = SimpleNamespace(bot=self, guild=self.modmail_guild)
        converter = commands.EmojiConverter()

        blocked_emoji = self.config.get('blocked_emoji', '🚫')
        sent_emoji = self.config.get('sent_emoji', '✅')

        if blocked_emoji not in UNICODE_EMOJI:
            try:
                blocked_emoji = await converter.convert(
                    ctx, blocked_emoji.strip(':')
                )
            except commands.BadArgument:
                pass

        if sent_emoji not in UNICODE_EMOJI:
            try:
                sent_emoji = await converter.convert(
                    ctx, sent_emoji.strip(':')
                )
            except commands.BadArgument:
                pass

        if str(message.author.id) in self.blocked_users:
            reaction = blocked_emoji
        else:
            reaction = sent_emoji

        try:
            await message.add_reaction(reaction)
        except (discord.HTTPException, discord.InvalidArgument):
            pass

        if str(message.author.id) not in self.blocked_users:
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

        ctx.thread = await self.threads.find(channel=ctx.channel)

        prefixes = await self.get_prefix()

        invoked_prefix = discord.utils.find(view.skip_string, prefixes)
        if invoked_prefix is None:
            return ctx

        invoker = view.get_word().lower()

        # Check if there is any aliases being called.
        alias = self.config.get('aliases', {}).get(invoker)
        if alias is not None:
            ctx._alias_invoked = True
            len_ = len(f'{invoked_prefix}{invoker}')
            view = StringView(f'{alias}{ctx.message.content[len_:]}')
            ctx.view = view
            invoker = view.get_word()

        ctx.invoked_with = invoker
        ctx.prefix = self.prefix  # Sane prefix (No mentions)
        ctx.command = self.all_commands.get(invoker)

        has_ai = hasattr(ctx, '_alias_invoked')
        if ctx.command is self.get_command('eval') and has_ai:
            # ctx.command.checks = None # Let anyone use the command.
            pass

        return ctx

    async def on_message(self, message):
        if message.type == discord.MessageType.pins_add and \
                message.author == self.user:
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
            await self.api.append_log(message, type_='internal')
        elif ctx.invoked_with:
            exc = commands.CommandNotFound(
                'Command "{}" is not found'.format(ctx.invoked_with)
            )
            self.dispatch('command_error', ctx, exc)
    
    async def on_typing(self, channel, user, when):
        if isinstance(channel, discord.DMChannel):
            if not self.config.get('user_typing'):
                return
            thread = await self.threads.find(recipient=user)
            if thread:
                await thread.channel.trigger_typing()
        else:
            if not self.config.get('mod_typing'):
                return
            thread = await self.threads.find(channel=channel)
            if thread and thread.recipient:
                await thread.recipient.trigger_typing()

    async def on_guild_channel_delete(self, channel):
        if channel.guild != self.modmail_guild:
            return

        audit_logs = self.modmail_guild.audit_logs()
        entry = await audit_logs.find(lambda e: e.target.id == channel.id)
        mod = entry.user

        if mod == self.user:
            return

        if not isinstance(channel, discord.TextChannel):
            if int(self.config.get('main_category_id')) == channel.id:
                await self.config.update({
                    'main_category_id': None
                })
            return

        if int(self.config.get('log_channel_id')) == channel.id:
            await self.config.update({
                'log_channel_id': None
            })
            return

        thread = await self.threads.find(channel=channel)
        if not thread:
            return

        await thread.close(closer=mod, silent=True, delete_channel=False)

    async def on_message_delete(self, message):
        """Support for deleting linked messages"""
        if message.embeds and not isinstance(message.channel,
                                             discord.DMChannel):
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
                        await self.api.edit_message(str(after.id),
                                                    after.content)
                        break

    async def on_error(self, event_method, *args, **kwargs):
        logger.error(error('Ignoring exception in {}'.format(event_method)))
        logger.error(error('Unexpected exception:'), exc_info=sys.exc_info())

    async def on_command_error(self, context, exception):
        if isinstance(exception, (commands.MissingRequiredArgument,
                                  commands.UserInputError)):
            await context.invoke(self.get_command('help'),
                                 command=str(context.command))
        elif isinstance(exception, commands.CommandNotFound):
            logger.warning(error('CommandNotFound: ' + str(exception)))
        else:
            logger.error(error('Unexpected exception:'), exc_info=exception)

    @staticmethod
    def overwrites(ctx):
        """Permission overwrites for the guild."""
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            ),
            ctx.guild.me: discord.PermissionOverwrite(
                read_messages=True
            )
        }

        for role in ctx.guild.roles:
            if role.permissions.manage_guild:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True
                )
        return overwrites

    async def validate_api_token(self):
        try:
            self.config.modmail_api_token
        except KeyError:
            logger.critical(error(f'MODMAIL_API_TOKEN not found.'))
            logger.critical(error('Set a config variable called '
                                  'MODMAIL_API_TOKEN with a token from '
                                  'https://dashboard.modmail.tk.'))
            logger.critical(error('If you want to self-host logs, '
                                  'input a MONGO_URI config variable.'))
            logger.critical(error('A Modmail API token is not needed '
                                  'if you are self-hosting logs.'))

            return await self.logout()
        else:
            valid = await self.api.validate_token()
            if not valid:
                logger.critical(error('Invalid MODMAIL_API_TOKEN - get one '
                                      'from https://dashboard.modmail.tk'))
                return await self.logout()

        user = await self.api.get_user_info()
        username = user['user']['username']
        logger.info(info('Validated token.'))
        logger.info(info('GitHub user: ' + username))

    async def validate_database_connection(self):
        try:
            await self.db.command('buildinfo')
        except Exception as exc:
            logger.critical(error('Something went wrong '
                                  'while connecting to the database.'))
            logger.critical(error(f'{type(exc).__name__}: {str(exc)}'))
            return await self.logout()
        else:
            logger.info(info('Successfully connected to the database.'))

    async def data_loop(self):
        await self.wait_until_ready()
        self.owner = (await self.application_info()).owner

        while not self.is_closed():
            data = {
                "owner_name": str(self.owner),
                "owner_id": self.owner.id,
                "bot_id": self.user.id,
                "bot_name": str(self.user),
                "avatar_url": self.user.avatar_url,
                "guild_id": self.guild_id,
                "guild_name": self.guild.name,
                "member_count": len(self.guild.members),
                "uptime": (datetime.utcnow() -
                           self.start_time).total_seconds(),
                "latency": f'{self.ws.latency * 1000:.4f}',
                "version": self.version,
                # TODO: change to `self_hosted`
                "selfhosted": self.self_hosted,
                "last_updated": str(datetime.utcnow())
            }

            await self.api.post_metadata(data)
            await asyncio.sleep(3600)

    async def autoupdate_loop(self):
        await self.wait_until_ready()

        if self.config.get('disable_autoupdates'):
            logger.warning(info('Autoupdates disabled.'))
            logger.warning(LINE)
            return

        if self.self_hosted and not self.config.get('github_access_token'):
            logger.warning(info('GitHub access token not found.'))
            logger.warning(info('Autoupdates disabled.'))
            logger.warning(LINE)
            return

        while not self.is_closed():
            metadata = await self.api.get_metadata()

            if metadata['latest_version'] != self.version:
                data = await self.api.update_repository()

                embed = discord.Embed(color=discord.Color.green())

                commit_data = data['data']
                user = data['user']
                embed.set_author(name=user['username'] + ' - Updating Bot',
                                 icon_url=user['avatar_url'],
                                 url=user['url'])
                embed.set_footer(text=f"Updating Modmail v{self.version} "
                                      f"-> v{metadata['latest_version']}")

                changelog = await Changelog.from_url(self)
                latest = changelog.latest_version
                embed.description = latest.description
                for name, value in latest.fields.items():
                    embed.add_field(name=name, value=value)

                if commit_data:
                    message = commit_data['commit']['message']
                    html_url = commit_data["html_url"]
                    short_sha = commit_data['sha'][:6]
                    embed.add_field(name='Merge Commit',
                                    value=f"[`{short_sha}`]({html_url}) "
                                    f"{message} - {user['username']}")
                    logger.info(info('Updating bot.'))
                    channel = self.log_channel
                    await channel.send(embed=embed)

            await asyncio.sleep(3600)


if __name__ == '__main__':
    if os.name != 'nt':
        import uvloop
        uvloop.install()
    bot = ModmailBot()  # pylint: disable=invalid-name
    bot.run()
