"""
License

Copyright (c) 2017-2019 kyb3r

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including the rights to use, copy, modify 
and distribute copies of the Software, and to permit persons to whom the Software 
is furnished to do so, subject to the following terms and conditions: 

- The above copyright notice shall be included in all copies of the Software.

You may not:
  - Claim credit for, or refuse to give credit to the creator(s) of the Software.
  - Sell copies of the Software and of derivative works.
  - Modify the original Software to contain hidden harmful content. 
 
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

__version__ = "2.24.0"

import asyncio
import logging
import os
import re
import sys
import typing

from datetime import datetime
from types import SimpleNamespace

import discord
from discord.ext import commands
from discord.ext.commands.view import StringView

import isodate

from aiohttp import ClientSession
from colorama import init, Fore, Style
from emoji import UNICODE_EMOJI
from motor.motor_asyncio import AsyncIOMotorClient
from pkg_resources import parse_version

from core.changelog import Changelog
from core.clients import ApiClient, PluginDatabaseClient
from core.config import ConfigManager
from core.utils import info, error, human_join
from core.models import PermissionLevel
from core.thread import ThreadManager
from core.time import human_timedelta

init()

logger = logging.getLogger("Modmail")
logger.setLevel(logging.INFO)

ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.INFO)
formatter = logging.Formatter("%(filename)s - %(levelname)s: %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


class FileFormatter(logging.Formatter):
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

    def format(self, record):
        record.msg = self.ansi_escape.sub("", record.msg)
        return super().format(record)


temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
if not os.path.exists(temp_dir):
    os.mkdir(temp_dir)

ch_debug = logging.FileHandler(os.path.join(temp_dir, "logs.log"), mode="a+")

ch_debug.setLevel(logging.DEBUG)
formatter_debug = FileFormatter(
    "%(asctime)s %(filename)s - " "%(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
ch_debug.setFormatter(formatter_debug)
logger.addHandler(ch_debug)

LINE = Fore.BLACK + Style.BRIGHT + "-------------------------" + Style.RESET_ALL


class ModmailBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=None)  # implemented in `get_prefix`
        self._threads = None
        self._session = None
        self._config = None
        self._db = None
        self.start_time = datetime.utcnow()
        self._connected = asyncio.Event()

        self._configure_logging()
        # TODO: Raise fatal error if mongo_uri or other essentials are not found
        self._db = AsyncIOMotorClient(self.config.mongo_uri).modmail_bot
        self._api = ApiClient(self)
        self.plugin_db = PluginDatabaseClient(self)

        self.metadata_task = self.loop.create_task(self.metadata_loop())
        self.autoupdate_task = self.loop.create_task(self.autoupdate_loop())
        self._load_extensions()

    @property
    def uptime(self) -> str:
        now = datetime.utcnow()
        delta = now - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        fmt = "{h}h {m}m {s}s"
        if days:
            fmt = "{d}d " + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    def _configure_logging(self):
        level_text = self.config.log_level.upper()
        logging_levels = {
            "CRITICAL": logging.CRITICAL,
            "ERROR": logging.ERROR,
            "WARNING": logging.WARNING,
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG,
        }

        log_level = logging_levels.get(level_text)
        logger.info(LINE)
        if log_level is not None:
            logger.setLevel(log_level)
            ch.setLevel(log_level)
            logger.info(info("Logging level: " + level_text))
        else:
            logger.info(error("Invalid logging level set. "))
            logger.info(info("Using default logging level: INFO"))

    @property
    def version(self) -> str:
        return __version__

    @property
    def db(self) -> typing.Optional[AsyncIOMotorClient]:
        return self._db

    @property
    def api(self) -> ApiClient:
        return self._api

    @property
    def config(self) -> ConfigManager:
        if self._config is None:
            self._config = ConfigManager(self)
        return self._config

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            self._session = ClientSession(loop=self.loop)
        return self._session

    @property
    def threads(self) -> ThreadManager:
        if self._threads is None:
            self._threads = ThreadManager(self)
        return self._threads

    async def get_prefix(self, message=None):
        return [self.prefix, f"<@{self.user.id}> ", f"<@!{self.user.id}> "]

    def _load_extensions(self):
        """Adds commands automatically"""
        logger.info(LINE)
        logger.info(info("┌┬┐┌─┐┌┬┐┌┬┐┌─┐┬┬"))
        logger.info(info("││││ │ │││││├─┤││"))
        logger.info(info("┴ ┴└─┘─┴┘┴ ┴┴ ┴┴┴─┘"))
        logger.info(info(f"v{__version__}"))
        logger.info(info("Authors: kyb3r, fourjr, Taaku18"))
        logger.info(LINE)

        for file in os.listdir("cogs"):
            if not file.endswith(".py"):
                continue
            cog = f"cogs.{file[:-3]}"
            logger.info(info(f"Loading {cog}"))
            try:
                self.load_extension(cog)
            except Exception:
                logger.exception(error(f"Failed to load {cog}"))

    def run(self, *args, **kwargs):
        try:
            self.loop.run_until_complete(self.start(self.token))
        except discord.LoginFailure:
            logger.critical(error("Invalid token"))
        except KeyboardInterrupt:
            pass
        except Exception:
            logger.critical(error("Fatal exception"), exc_info=True)
        finally:
            try:
                self.metadata_task.cancel()
                self.loop.run_until_complete(self.metadata_task)
            except asyncio.CancelledError:
                logger.debug(info("data_task has been cancelled."))
            try:
                self.autoupdate_task.cancel()
                self.loop.run_until_complete(self.autoupdate_task)
            except asyncio.CancelledError:
                logger.debug(info("autoupdate_task has been cancelled."))

            self.loop.run_until_complete(self.logout())
            for task in asyncio.Task.all_tasks():
                task.cancel()
            try:
                self.loop.run_until_complete(asyncio.gather(*asyncio.Task.all_tasks()))
            except asyncio.CancelledError:
                logger.debug(info("All pending tasks has been cancelled."))
            finally:
                self.loop.run_until_complete(self.session.close())
                self.loop.close()
                logger.info(error(" - Shutting down bot - "))

    async def is_owner(self, user: discord.User) -> bool:
        raw = str(self.config.get("owners", "0")).split(",")
        allowed = {int(x) for x in raw}
        return (user.id in allowed) or await super().is_owner(user)

    @property
    def log_channel(self) -> typing.Optional[discord.TextChannel]:
        channel_id = self.config.get("log_channel_id")
        if channel_id is not None:
            return self.get_channel(int(channel_id))
        if self.main_category is not None:
            return self.main_category.channels[0]
        return None

    @property
    def snippets(self) -> typing.Dict[str, str]:
        return {k: v for k, v in self.config.get("snippets", {}).items() if v}

    @property
    def aliases(self) -> typing.Dict[str, str]:
        return {k: v for k, v in self.config.get("aliases", {}).items() if v}

    @property
    def token(self) -> str:
        return self.config.token

    @property
    def guild_id(self) -> int:
        return int(self.config.guild_id)

    @property
    def guild(self) -> discord.Guild:
        """
        The guild that the bot is serving
        (the server where users message it from)
        """
        return discord.utils.get(self.guilds, id=self.guild_id)

    @property
    def modmail_guild(self) -> discord.Guild:
        """
        The guild that the bot is operating in
        (where the bot is creating threads)
        """
        modmail_guild_id = self.config.get("modmail_guild_id")
        if not modmail_guild_id:
            return self.guild
        return discord.utils.get(self.guilds, id=int(modmail_guild_id))

    @property
    def using_multiple_server_setup(self) -> bool:
        return self.modmail_guild != self.guild

    @property
    def main_category(self) -> typing.Optional[discord.TextChannel]:
        category_id = self.config.get("main_category_id")
        if category_id is not None:
            return discord.utils.get(self.modmail_guild.categories, id=int(category_id))

        if self.modmail_guild:
            return discord.utils.get(self.modmail_guild.categories, name="Modmail")
        return None

    @property
    def blocked_users(self) -> typing.Dict[str, str]:
        return self.config.get("blocked", {})

    @property
    def prefix(self) -> str:
        return self.config.get("prefix", "?")

    @property
    def mod_color(self) -> typing.Union[discord.Color, int]:
        color = self.config.get("mod_color")
        if not color:
            return discord.Color.green()
        try:
            color = int(color.lstrip("#"), base=16)
        except ValueError:
            logger.error(error("Invalid mod_color provided"))
            return discord.Color.green()
        else:
            return color

    @property
    def recipient_color(self) -> typing.Union[discord.Color, int]:
        color = self.config.get("recipient_color")
        if not color:
            return discord.Color.gold()
        try:
            color = int(color.lstrip("#"), base=16)
        except ValueError:
            logger.error(error("Invalid recipient_color provided"))
            return discord.Color.gold()
        else:
            return color

    @property
    def main_color(self) -> typing.Union[discord.Color, int]:
        color = self.config.get("main_color")
        if not color:
            return discord.Color.blurple()
        try:
            color = int(color.lstrip("#"), base=16)
        except ValueError:
            logger.error(error("Invalid main_color provided"))
            return discord.Color.blurple()
        else:
            return color

    async def on_connect(self):
        logger.info(LINE)
        await self.validate_database_connection()
        logger.info(LINE)
        logger.info(info("Connected to gateway."))

        await self.config.refresh()
        if self.db:
            await self.setup_indexes()
        self._connected.set()

    async def setup_indexes(self):
        """Setup text indexes so we can use the $search operator"""
        coll = self.db.logs
        index_name = "messages.content_text_messages.author.name_text_key_text"

        index_info = await coll.index_information()

        # Backwards compatibility
        old_index = "messages.content_text_messages.author.name_text"
        if old_index in index_info:
            logger.info(info(f"Dropping old index: {old_index}"))
            await coll.drop_index(old_index)

        if index_name not in index_info:
            logger.info(info('Creating "text" index for logs collection.'))
            logger.info(info("Name: " + index_name))
            await coll.create_index(
                [
                    ("messages.content", "text"),
                    ("messages.author.name", "text"),
                    ("key", "text"),
                ]
            )

    async def on_ready(self):
        """Bot startup, sets uptime."""
        await self._connected.wait()
        logger.info(LINE)
        logger.info(info("Client ready."))
        logger.info(LINE)
        logger.info(info(f"Logged in as: {self.user}"))
        logger.info(info(f"Prefix: {self.prefix}"))
        logger.info(info(f"User ID: {self.user.id}"))
        logger.info(info(f"Guild ID: {self.guild.id if self.guild else 0}"))
        logger.info(LINE)

        if not self.guild:
            logger.error(error("WARNING - The GUILD_ID " "provided does not exist!"))
        else:
            await self.threads.populate_cache()

        # Wait until config cache is populated with stuff from db
        await self.config.wait_until_ready()

        # closures
        closures = self.config.closures.copy()
        logger.info(
            info(f"There are {len(closures)} thread(s) " "pending to be closed.")
        )

        for recipient_id, items in closures.items():
            after = (
                datetime.fromisoformat(items["time"]) - datetime.utcnow()
            ).total_seconds()
            if after < 0:
                after = 0

            thread = await self.threads.find(recipient_id=int(recipient_id))

            if not thread:
                # If the channel is deleted
                self.config.closures.pop(str(recipient_id))
                await self.config.update()
                continue

            await thread.close(
                closer=self.get_user(items["closer_id"]),
                after=after,
                silent=items["silent"],
                delete_channel=items["delete_channel"],
                message=items["message"],
            )

        logger.info(LINE)

    async def convert_emoji(self, name: str) -> str:
        ctx = SimpleNamespace(bot=self, guild=self.modmail_guild)
        converter = commands.EmojiConverter()

        if name not in UNICODE_EMOJI:
            try:
                name = await converter.convert(ctx, name.strip(":"))
            except commands.BadArgument:
                logger.warning(info("%s is not a valid emoji."), name)
                raise
        return name

    async def retrieve_emoji(self) -> typing.Tuple[str, str]:

        sent_emoji = self.config.get("sent_emoji", "✅")
        blocked_emoji = self.config.get("blocked_emoji", "🚫")

        if sent_emoji != "disable":
            try:
                sent_emoji = await self.convert_emoji(sent_emoji)
            except commands.BadArgument:
                logger.warning(info("Removed sent emoji (%s)."), sent_emoji)
                del self.config.cache["sent_emoji"]
                await self.config.update()
                sent_emoji = "✅"

        if blocked_emoji != "disable":
            try:
                blocked_emoji = await self.convert_emoji(blocked_emoji)
            except commands.BadArgument:
                logger.warning(info("Removed blocked emoji (%s)."), blocked_emoji)
                del self.config.cache["blocked_emoji"]
                await self.config.update()
                blocked_emoji = "🚫"

        return sent_emoji, blocked_emoji

    async def process_modmail(self, message: discord.Message) -> None:
        """Processes messages sent to the bot."""
        sent_emoji, blocked_emoji = await self.retrieve_emoji()
        now = datetime.utcnow()

        account_age = self.config.get("account_age")
        guild_age = self.config.get("guild_age")
        if account_age is None:
            account_age = isodate.duration.Duration()
        else:
            try:
                account_age = isodate.parse_duration(account_age)
            except isodate.ISO8601Error:
                logger.warning(
                    "The account age limit needs to be a "
                    "ISO-8601 duration formatted duration string "
                    'greater than 0 days, not "%s".',
                    str(account_age),
                )
                del self.config.cache["account_age"]
                await self.config.update()
                account_age = isodate.duration.Duration()

        if guild_age is None:
            guild_age = isodate.duration.Duration()
        else:
            try:
                guild_age = isodate.parse_duration(guild_age)
            except isodate.ISO8601Error:
                logger.warning(
                    "The guild join age limit needs to be a "
                    "ISO-8601 duration formatted duration string "
                    'greater than 0 days, not "%s".',
                    str(guild_age),
                )
                del self.config.cache["guild_age"]
                await self.config.update()
                guild_age = isodate.duration.Duration()

        reason = self.blocked_users.get(str(message.author.id))
        if reason is None:
            reason = ""

        try:
            min_account_age = message.author.created_at + account_age
        except ValueError as exc:
            logger.warning(exc.args[0])
            del self.config.cache["account_age"]
            await self.config.update()
            min_account_age = now

        try:
            member = self.guild.get_member(message.author.id)
            if member:
                min_guild_age = member.joined_at + guild_age
            else:
                min_guild_age = now
        except ValueError as exc:
            logger.warning(exc.args[0])
            del self.config.cache["guild_age"]
            await self.config.update()
            min_guild_age = now

        if min_account_age > now:
            # User account has not reached the required time
            reaction = blocked_emoji
            changed = False
            delta = human_timedelta(min_account_age)

            if str(message.author.id) not in self.blocked_users:
                new_reason = (
                    f"System Message: New Account. Required to wait for {delta}."
                )
                self.config.blocked[str(message.author.id)] = new_reason
                await self.config.update()
                changed = True

            if reason.startswith("System Message: New Account.") or changed:
                await message.channel.send(
                    embed=discord.Embed(
                        title="Message not sent!",
                        description=f"Your must wait for {delta} "
                        f"before you can contact {self.user.mention}.",
                        color=discord.Color.red(),
                    )
                )

        elif min_guild_age > now:
            # User has not stayed in the guild for long enough
            reaction = blocked_emoji
            changed = False
            delta = human_timedelta(min_guild_age)

            if str(message.author.id) not in self.blocked_users:
                new_reason = (
                    f"System Message: Recently Joined. Required to wait for {delta}."
                )
                self.config.blocked[str(message.author.id)] = new_reason
                await self.config.update()
                changed = True

            if reason.startswith("System Message: Recently Joined.") or changed:
                await message.channel.send(
                    embed=discord.Embed(
                        title="Message not sent!",
                        description=f"Your must wait for {delta} "
                        f"before you can contact {self.user.mention}.",
                        color=discord.Color.red(),
                    )
                )

        elif str(message.author.id) in self.blocked_users:
            reaction = blocked_emoji
            if reason.startswith("System Message: New Account.") or reason.startswith(
                "System Message: Recently Joined."
            ):
                # Met the age limit already
                reaction = sent_emoji
                del self.config.blocked[str(message.author.id)]
                await self.config.update()
            else:
                end_time = re.search(r"%(.+?)%$", reason)
                if end_time is not None:
                    after = (
                        datetime.fromisoformat(end_time.group(1)) - now
                    ).total_seconds()
                    if after <= 0:
                        # No longer blocked
                        reaction = sent_emoji
                        del self.config.blocked[str(message.author.id)]
                        await self.config.update()
        else:
            reaction = sent_emoji

        if reaction != "disable":
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
        alias = self.config.get("aliases", {}).get(invoker)
        if alias is not None:
            ctx._alias_invoked = True
            len_ = len(f"{invoked_prefix}{invoker}")
            view = StringView(f"{alias}{ctx.message.content[len_:]}")
            ctx.view = view
            invoker = view.get_word()

        ctx.invoked_with = invoker
        ctx.prefix = self.prefix  # Sane prefix (No mentions)
        ctx.command = self.all_commands.get(invoker)

        return ctx

    async def update_perms(
        self, name: typing.Union[PermissionLevel, str], value: int, add: bool = True
    ) -> None:
        if isinstance(name, PermissionLevel):
            permissions = self.config.level_permissions
            name = name.name
        else:
            permissions = self.config.command_permissions
        if name not in permissions:
            if add:
                permissions[name] = [value]
        else:
            if add:
                if value not in permissions[name]:
                    permissions[name].append(value)
            else:
                if value in permissions[name]:
                    permissions[name].remove(value)
        logger.info(info(f"Updating permissions for {name}, {value} (add={add})."))
        await self.config.update()

    async def on_message(self, message):
        if message.type == discord.MessageType.pins_add and message.author == self.user:
            await message.delete()

        if message.author.bot:
            return

        if isinstance(message.channel, discord.DMChannel):
            return await self.process_modmail(message)

        prefix = self.prefix

        if message.content.startswith(prefix):
            cmd = message.content[len(prefix) :].strip()
            if cmd in self.snippets:
                thread = await self.threads.find(channel=message.channel)
                snippet = self.snippets[cmd]
                if thread:
                    snippet = snippet.format(recipient=thread.recipient)
                message.content = f"{prefix}reply {snippet}"

        ctx = await self.get_context(message)
        if ctx.command:
            return await self.invoke(ctx)

        thread = await self.threads.find(channel=ctx.channel)
        if thread is not None:
            if self.config.get("reply_without_command"):
                await thread.reply(message)
            else:
                await self.api.append_log(message, type_="internal")
        elif ctx.invoked_with:
            exc = commands.CommandNotFound(
                'Command "{}" is not found'.format(ctx.invoked_with)
            )
            self.dispatch("command_error", ctx, exc)

    async def on_typing(self, channel, user, _):
        if user.bot:
            return
        if isinstance(channel, discord.DMChannel):
            if not self.config.get("user_typing"):
                return
            thread = await self.threads.find(recipient=user)
            if thread:
                await thread.channel.trigger_typing()
        else:
            if not self.config.get("mod_typing"):
                return
            thread = await self.threads.find(channel=channel)
            if thread and thread.recipient:
                await thread.recipient.trigger_typing()

    async def on_raw_reaction_add(self, payload):

        user = self.get_user(payload.user_id)

        if user.bot:
            return

        channel = self.get_channel(payload.channel_id)

        if not channel:  # dm channel not in internal cache
            _thread = await self.threads.find(recipient=user)
            if not _thread:
                return
            channel = await _thread.recipient.create_dm()

        message = await channel.fetch_message(payload.message_id)
        reaction = payload.emoji

        close_emoji = await self.convert_emoji(self.config.get("close_emoji", "🔒"))

        if isinstance(channel, discord.DMChannel) and str(reaction) == str(
            close_emoji
        ):  # closing thread
            thread = await self.threads.find(recipient=user)
            ts = message.embeds[0].timestamp if message.embeds else None
            if thread and ts == thread.channel.created_at:
                # the reacted message is the corresponding thread creation embed
                if not self.config.get("disable_recipient_thread_close"):
                    await thread.close(closer=user)
        elif not isinstance(channel, discord.DMChannel):
            if not message.embeds:
                return
            message_id = str(message.embeds[0].author.url).split("/")[-1]
            if message_id.isdigit():
                thread = await self.threads.find(channel=message.channel)
                channel = thread.recipient.dm_channel
                if not channel:
                    channel = await thread.recipient.create_dm()
                async for msg in channel.history():
                    if msg.id == int(message_id):
                        await msg.add_reaction(reaction)

    async def on_guild_channel_delete(self, channel):
        if channel.guild != self.modmail_guild:
            return

        audit_logs = self.modmail_guild.audit_logs()
        entry = await audit_logs.find(lambda e: e.target.id == channel.id)
        mod = entry.user

        if mod == self.user:
            return

        if not isinstance(channel, discord.TextChannel):
            if int(self.config.get("main_category_id")) == channel.id:
                await self.config.update({"main_category_id": None})
            return

        if int(self.config.get("log_channel_id")) == channel.id:
            await self.config.update({"log_channel_id": None})
            return

        thread = await self.threads.find(channel=channel)
        if not thread:
            return

        await thread.close(closer=mod, silent=True, delete_channel=False)

    async def on_member_remove(self, member):
        thread = await self.threads.find(recipient=member)
        if thread:
            embed = discord.Embed(
                description="The recipient has left the server.",
                color=discord.Color.red(),
            )
            await thread.channel.send(embed=embed)

    async def on_member_join(self, member):
        thread = await self.threads.find(recipient=member)
        if thread:
            embed = discord.Embed(
                description="The recipient has joined the server.", color=self.mod_color
            )
            await thread.channel.send(embed=embed)

    async def on_message_delete(self, message):
        """Support for deleting linked messages"""
        if message.embeds and not isinstance(message.channel, discord.DMChannel):
            message_id = str(message.embeds[0].author.url).split("/")[-1]
            if message_id.isdigit():
                thread = await self.threads.find(channel=message.channel)

                channel = thread.recipient.dm_channel

                async for msg in channel.history():
                    if msg.embeds and msg.embeds[0].author:
                        url = str(msg.embeds[0].author.url)
                        if message_id == url.split("/")[-1]:
                            return await msg.delete()

    async def on_bulk_message_delete(self, messages):
        await discord.utils.async_all(self.on_message_delete(msg) for msg in messages)

    async def on_message_edit(self, before, after):
        if before.author.bot:
            return
        if isinstance(before.channel, discord.DMChannel):
            thread = await self.threads.find(recipient=before.author)
            async for msg in thread.channel.history():
                if msg.embeds:
                    embed = msg.embeds[0]
                    matches = str(embed.author.url).split("/")
                    if matches and matches[-1] == str(before.id):
                        embed.description = after.content
                        await msg.edit(embed=embed)
                        await self.api.edit_message(str(after.id), after.content)
                        break

    async def on_error(self, event_method, *args, **kwargs):
        logger.error(error("Ignoring exception in {}".format(event_method)))
        logger.error(error("Unexpected exception:"), exc_info=sys.exc_info())

    async def on_command_error(self, context, exception):
        if isinstance(exception, commands.BadUnionArgument):
            msg = "Could not find the specified " + human_join(
                [c.__name__ for c in exception.converters]
            )
            await context.trigger_typing()
            await context.send(
                embed=discord.Embed(color=discord.Color.red(), description=msg)
            )

        elif isinstance(exception, commands.BadArgument):
            await context.trigger_typing()
            await context.send(
                embed=discord.Embed(
                    color=discord.Color.red(), description=str(exception)
                )
            )
        elif isinstance(exception, commands.CommandNotFound):
            logger.warning(error("CommandNotFound: " + str(exception)))
        elif isinstance(exception, commands.MissingRequiredArgument):
            await context.send_help(context.command)
        elif isinstance(exception, commands.CheckFailure):
            for check in context.command.checks:
                if not await check(context) and hasattr(check, "fail_msg"):
                    await context.send(
                        embed=discord.Embed(
                            color=discord.Color.red(), description=check.fail_msg
                        )
                    )
            logger.warning(error("CheckFailure: " + str(exception)))
        else:
            logger.error(error("Unexpected exception:"), exc_info=exception)

    @staticmethod
    def overwrites(ctx: commands.Context) -> dict:
        """Permission overwrites for the guild."""
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
        }

        for role in ctx.guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True)
        return overwrites

    async def validate_database_connection(self):
        try:
            await self.db.command("buildinfo")
        except Exception as exc:
            logger.critical(
                error("Something went wrong " "while connecting to the database.")
            )
            message = f"{type(exc).__name__}: {str(exc)}"
            logger.critical(error(message))

            if "ServerSelectionTimeoutError" in message:
                logger.critical(
                    error(
                        "This may have been caused by not whitelisting "
                        "IPs correctly. Make sure to whitelist all "
                        "IPs (0.0.0.0/0) https://i.imgur.com/mILuQ5U.png"
                    )
                )

            if "OperationFailure" in message:
                logger.critical(
                    error(
                        "This is due to having invalid credentials in your MONGO_URI."
                    )
                )
                logger.critical(
                    error(
                        "Recheck the username/password and make sure to url encode them. "
                        "https://www.urlencoder.io/"
                    )
                )

            return await self.logout()
        else:
            logger.info(info("Successfully connected to the database."))

    async def autoupdate_loop(self):
        await self.wait_until_ready()

        if self.config.get("disable_autoupdates"):
            logger.warning(info("Autoupdates disabled."))
            logger.info(LINE)
            return

        if not self.config.get("github_access_token"):
            logger.warning(info("GitHub access token not found."))
            logger.warning(info("Autoupdates disabled."))
            logger.info(LINE)
            return

        logger.info(info("Autoupdate loop started."))

        while not self.is_closed():
            changelog = await Changelog.from_url(self)
            latest = changelog.latest_version

            if parse_version(self.version) < parse_version(latest.version):
                data = await self.api.update_repository()

                embed = discord.Embed(color=discord.Color.green())

                commit_data = data["data"]
                user = data["user"]
                embed.set_author(
                    name=user["username"] + " - Updating Bot",
                    icon_url=user["avatar_url"],
                    url=user["url"],
                )

                embed.set_footer(
                    text=f"Updating Modmail v{self.version} " f"-> v{latest.version}"
                )

                embed.description = latest.description
                for name, value in latest.fields.items():
                    embed.add_field(name=name, value=value)

                if commit_data:
                    message = commit_data["commit"]["message"]
                    html_url = commit_data["html_url"]
                    short_sha = commit_data["sha"][:6]
                    embed.add_field(
                        name="Merge Commit",
                        value=f"[`{short_sha}`]({html_url}) "
                        f"{message} - {user['username']}",
                    )
                    logger.info(info("Bot has been updated."))
                    channel = self.log_channel
                    await channel.send(embed=embed)

            await asyncio.sleep(3600)

    async def metadata_loop(self):
        await self.wait_until_ready()
        if not self.guild:
            return

        owner = (await self.application_info()).owner

        while not self.is_closed():
            data = {
                "owner_name": str(owner),
                "owner_id": owner.id,
                "bot_id": self.user.id,
                "bot_name": str(self.user),
                "avatar_url": str(self.user.avatar_url),
                "guild_id": self.guild_id,
                "guild_name": self.guild.name,
                "member_count": len(self.guild.members),
                "uptime": (datetime.utcnow() - self.start_time).total_seconds(),
                "latency": f"{self.ws.latency * 1000:.4f}",
                "version": self.version,
                "selfhosted": True,
                "last_updated": str(datetime.utcnow()),
            }

            async with self.session.post("https://api.modmail.tk/metadata", json=data):
                logger.debug(info("Uploading metadata to Modmail server."))

            await asyncio.sleep(3600)


if __name__ == "__main__":
    if os.name != "nt":
        import uvloop
        uvloop.install()
    bot = ModmailBot()
    bot.run()
