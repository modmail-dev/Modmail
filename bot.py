__version__ = "3.3.0-dev6"

import asyncio
import logging
import os
import re
import sys
import typing
from datetime import datetime
from itertools import zip_longest
from types import SimpleNamespace

import discord
from discord.ext import commands, tasks
from discord.ext.commands.view import StringView

import isodate

from aiohttp import ClientSession
from emoji import UNICODE_EMOJI
from motor.motor_asyncio import AsyncIOMotorClient
from pkg_resources import parse_version
from pymongo.errors import ConfigurationError

try:
    # noinspection PyUnresolvedReferences
    from colorama import init

    init()
except ImportError:
    pass

from core import checks
from core.clients import ApiClient, PluginDatabaseClient
from core.config import ConfigManager
from core.utils import human_join, parse_alias
from core.models import PermissionLevel, SafeFormatter, getLogger, configure_logging
from core.thread import ThreadManager
from core.time import human_timedelta


logger = getLogger(__name__)

temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
if not os.path.exists(temp_dir):
    os.mkdir(temp_dir)


class ModmailBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=None)  # implemented in `get_prefix`
        self._session = None
        self._api = None
        self.metadata_loop = None
        self.formatter = SafeFormatter()
        self.loaded_cogs = ["cogs.modmail", "cogs.plugins", "cogs.utility"]
        self._connected = asyncio.Event()
        self.start_time = datetime.utcnow()

        self.config = ConfigManager(self)
        self.config.populate_cache()

        self.threads = ThreadManager(self)

        self.log_file_name = os.path.join(temp_dir, f"{self.token.split('.')[0]}.log")
        self._configure_logging()

        mongo_uri = self.config["mongo_uri"]
        if mongo_uri is None:
            logger.critical("A Mongo URI is necessary for the bot to function.")
            raise RuntimeError

        try:
            self.db = AsyncIOMotorClient(mongo_uri).modmail_bot
        except ConfigurationError as e:
            logger.critical(
                "Your MONGO_URI might be copied wrong, try re-copying from the source again. "
                "Otherwise noted in the following message:"
            )
            logger.critical(str(e))
            sys.exit(0)

        self.plugin_db = PluginDatabaseClient(self)
        self.startup()

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

        return self.formatter.format(fmt, d=days, h=hours, m=minutes, s=seconds)

    def startup(self):
        logger.line()
        logger.info("┌┬┐┌─┐┌┬┐┌┬┐┌─┐┬┬")
        logger.info("││││ │ │││││├─┤││")
        logger.info("┴ ┴└─┘─┴┘┴ ┴┴ ┴┴┴─┘")
        logger.info("v%s", __version__)
        logger.info("Authors: kyb3r, fourjr, Taaku18")
        logger.line()

        for cog in self.loaded_cogs:
            logger.debug("Loading %s.", cog)
            try:
                self.load_extension(cog)
                logger.debug("Successfully loaded %s.", cog)
            except Exception:
                logger.exception("Failed to load %s.", cog)
        logger.line("debug")

    def _configure_logging(self):
        level_text = self.config["log_level"].upper()
        logging_levels = {
            "CRITICAL": logging.CRITICAL,
            "ERROR": logging.ERROR,
            "WARNING": logging.WARNING,
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG,
        }
        logger.line()

        log_level = logging_levels.get(level_text)
        if log_level is None:
            log_level = self.config.remove("log_level")
            logger.warning("Invalid logging level set: %s.", level_text)
            logger.warning("Using default logging level: INFO.")
        else:
            logger.info("Logging level: %s", level_text)

        logger.info("Log file: %s", self.log_file_name)
        configure_logging(self.log_file_name, log_level)
        logger.debug("Successfully configured logging.")

    @property
    def version(self):
        return parse_version(__version__)

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            self._session = ClientSession(loop=self.loop)
        return self._session

    @property
    def api(self):
        if self._api is None:
            self._api = ApiClient(self)
        return self._api

    async def get_prefix(self, message=None):
        return [self.prefix, f"<@{self.user.id}> ", f"<@!{self.user.id}> "]

    def run(self, *args, **kwargs):
        try:
            self.loop.run_until_complete(self.start(self.token))
        except KeyboardInterrupt:
            pass
        except discord.LoginFailure:
            logger.critical("Invalid token")
        except Exception:
            logger.critical("Fatal exception", exc_info=True)
        finally:
            self.loop.run_until_complete(self.logout())
            for task in asyncio.all_tasks(self.loop):
                task.cancel()
            try:
                self.loop.run_until_complete(
                    asyncio.gather(*asyncio.all_tasks(self.loop))
                )
            except asyncio.CancelledError:
                logger.debug("All pending tasks has been cancelled.")
            finally:
                self.loop.run_until_complete(self.session.close())
                logger.error(" - Shutting down bot - ")

    @property
    def owner_ids(self):
        owner_ids = self.config["owners"]
        if owner_ids is not None:
            owner_ids = set(map(int, str(owner_ids).split(",")))
        if self.owner_id is not None:
            owner_ids.add(self.owner_id)
        permissions = self.config["level_permissions"].get(
            PermissionLevel.OWNER.name, []
        )
        for perm in permissions:
            owner_ids.add(int(perm))
        return owner_ids

    async def is_owner(self, user: discord.User) -> bool:
        if user.id in self.owner_ids:
            return True
        return await super().is_owner(user)

    @property
    def log_channel(self) -> typing.Optional[discord.TextChannel]:
        channel_id = self.config["log_channel_id"]
        if channel_id is not None:
            try:
                channel = self.get_channel(int(channel_id))
                if channel is not None:
                    return channel
            except ValueError:
                pass
            logger.debug("LOG_CHANNEL_ID was invalid, removed.")
            self.config.remove("log_channel_id")
        if self.main_category is not None:
            try:
                channel = self.main_category.channels[0]
                self.config["log_channel_id"] = channel.id
                logger.warning(
                    "No log channel set, setting #%s to be the log channel.",
                    channel.name,
                )
                return channel
            except IndexError:
                pass
        logger.warning(
            "No log channel set, set one with `%ssetup` or `%sconfig set log_channel_id <id>`.",
            self.prefix,
            self.prefix,
        )
        return None

    async def wait_for_connected(self) -> None:
        await self.wait_until_ready()
        await self._connected.wait()
        await self.config.wait_until_ready()

    @property
    def snippets(self) -> typing.Dict[str, str]:
        return self.config["snippets"]

    @property
    def aliases(self) -> typing.Dict[str, str]:
        return self.config["aliases"]

    @property
    def token(self) -> str:
        token = self.config["token"]
        if token is None:
            logger.critical(
                "TOKEN must be set, set this as bot token found on the Discord Developer Portal."
            )
            sys.exit(0)
        return token

    @property
    def guild_id(self) -> typing.Optional[int]:
        guild_id = self.config["guild_id"]
        if guild_id is not None:
            try:
                return int(str(guild_id))
            except ValueError:
                self.config.remove("guild_id")
                logger.critical("Invalid GUILD_ID set.")
        else:
            logger.debug("No GUILD_ID set.")
        return None

    @property
    def guild(self) -> typing.Optional[discord.Guild]:
        """
        The guild that the bot is serving
        (the server where users message it from)
        """
        return discord.utils.get(self.guilds, id=self.guild_id)

    @property
    def modmail_guild(self) -> typing.Optional[discord.Guild]:
        """
        The guild that the bot is operating in
        (where the bot is creating threads)
        """
        modmail_guild_id = self.config["modmail_guild_id"]
        if modmail_guild_id is None:
            return self.guild
        try:
            guild = discord.utils.get(self.guilds, id=int(modmail_guild_id))
            if guild is not None:
                return guild
        except ValueError:
            pass
        self.config.remove("modmail_guild_id")
        logger.critical("Invalid MODMAIL_GUILD_ID set.")
        return self.guild

    @property
    def using_multiple_server_setup(self) -> bool:
        return self.modmail_guild != self.guild

    @property
    def main_category(self) -> typing.Optional[discord.CategoryChannel]:
        if self.modmail_guild is not None:
            category_id = self.config["main_category_id"]
            if category_id is not None:
                try:
                    cat = discord.utils.get(
                        self.modmail_guild.categories, id=int(category_id)
                    )
                    if cat is not None:
                        return cat
                except ValueError:
                    pass
                self.config.remove("main_category_id")
                logger.debug("MAIN_CATEGORY_ID was invalid, removed.")
            cat = discord.utils.get(self.modmail_guild.categories, name="Modmail")
            if cat is not None:
                self.config["main_category_id"] = cat.id
                logger.debug(
                    'No main category set explicitly, setting category "Modmail" as the main category.'
                )
                return cat
        return None

    @property
    def blocked_users(self) -> typing.Dict[str, str]:
        return self.config["blocked"]

    @property
    def blocked_whitelisted_users(self) -> typing.List[str]:
        return self.config["blocked_whitelist"]

    @property
    def prefix(self) -> str:
        return str(self.config["prefix"])

    @property
    def mod_color(self) -> int:
        return self.config.get("mod_color")

    @property
    def recipient_color(self) -> int:
        return self.config.get("recipient_color")

    @property
    def main_color(self) -> int:
        return self.config.get("main_color")

    @property
    def error_color(self) -> int:
        return self.config.get("error_color")

    def command_perm(self, command_name: str) -> PermissionLevel:
        level = self.config["override_command_level"].get(command_name)
        if level is not None:
            try:
                return PermissionLevel[level.upper()]
            except KeyError:
                logger.warning(
                    "Invalid override_command_level for command %s.", command_name
                )
                self.config["override_command_level"].pop(command_name)

        command = self.get_command(command_name)
        if command is None:
            logger.debug("Command %s not found.", command_name)
            return PermissionLevel.INVALID
        level = next(
            (
                check.permission_level
                for check in command.checks
                if hasattr(check, "permission_level")
            ),
            None,
        )
        if level is None:
            logger.debug("Command %s does not have a permission level.", command_name)
            return PermissionLevel.INVALID
        return level

    async def on_connect(self):
        try:
            await self.validate_database_connection()
        except Exception:
            logger.debug("Logging out due to failed database connection.")
            return await self.logout()

        logger.debug("Connected to gateway.")
        await self.config.refresh()
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
            logger.info("Dropping old index: %s", old_index)
            await coll.drop_index(old_index)

        if index_name not in index_info:
            logger.info('Creating "text" index for logs collection.')
            logger.info("Name: %s", index_name)
            await coll.create_index(
                [
                    ("messages.content", "text"),
                    ("messages.author.name", "text"),
                    ("key", "text"),
                ]
            )
        logger.debug("Successfully configured and verified database indexes.")

    async def on_ready(self):
        """Bot startup, sets uptime."""

        # Wait until config cache is populated with stuff from db and on_connect ran
        await self.wait_for_connected()

        if self.guild is None:
            logger.error("Logging out due to invalid GUILD_ID.")
            return await self.logout()

        logger.line()
        logger.debug("Client ready.")
        logger.info("Logged in as: %s", self.user)
        logger.info("Bot ID: %s", self.user.id)
        owners = ", ".join(
            getattr(self.get_user(owner_id), "name", str(owner_id))
            for owner_id in self.owner_ids
        )
        logger.info("Owners: %s", owners)
        logger.info("Prefix: %s", self.prefix)
        logger.info("Guild Name: %s", self.guild.name)
        logger.info("Guild ID: %s", self.guild.id)
        if self.using_multiple_server_setup:
            logger.info("Receiving guild ID: %s", self.modmail_guild.id)
        logger.line()

        await self.threads.populate_cache()

        # closures
        closures = self.config["closures"]
        logger.info("There are %d thread(s) pending to be closed.", len(closures))
        logger.line()

        for recipient_id, items in tuple(closures.items()):
            after = (
                datetime.fromisoformat(items["time"]) - datetime.utcnow()
            ).total_seconds()
            if after < 0:
                after = 0

            thread = await self.threads.find(recipient_id=int(recipient_id))

            if not thread:
                # If the channel is deleted
                logger.debug("Failed to close thread for recipient %s.", recipient_id)
                self.config["closures"].pop(recipient_id)
                await self.config.update()
                continue

            logger.debug("Closing thread for recipient %s.", recipient_id)

            await thread.close(
                closer=self.get_user(items["closer_id"]),
                after=after,
                silent=items["silent"],
                delete_channel=items["delete_channel"],
                message=items["message"],
                auto_close=items.get("auto_close", False),
            )

        for log in await self.api.get_open_logs():
            if self.get_channel(int(log["channel_id"])) is None:
                logger.debug(
                    "Unable to resolve thread with channel %s.", log["channel_id"]
                )
                log_data = await self.api.post_log(
                    log["channel_id"],
                    {
                        "open": False,
                        "closed_at": str(datetime.utcnow()),
                        "close_message": "Channel has been deleted, no closer found.",
                        "closer": {
                            "id": str(self.user.id),
                            "name": self.user.name,
                            "discriminator": self.user.discriminator,
                            "avatar_url": str(self.user.avatar_url),
                            "mod": True,
                        },
                    },
                )
                if log_data:
                    logger.debug(
                        "Successfully closed thread with channel %s.", log["channel_id"]
                    )
                else:
                    logger.debug(
                        "Failed to close thread with channel %s, skipping.",
                        log["channel_id"],
                    )

        self.metadata_loop = tasks.Loop(
            self.post_metadata,
            seconds=0,
            minutes=0,
            hours=1,
            count=None,
            reconnect=True,
            loop=None,
        )
        self.metadata_loop.before_loop(self.before_post_metadata)
        self.metadata_loop.start()

    async def convert_emoji(self, name: str) -> str:
        ctx = SimpleNamespace(bot=self, guild=self.modmail_guild)
        converter = commands.EmojiConverter()

        if name not in UNICODE_EMOJI:
            try:
                name = await converter.convert(ctx, name.strip(":"))
            except commands.BadArgument as e:
                logger.warning("%s is not a valid emoji. %s.", str(e))
                raise
        return name

    async def retrieve_emoji(self) -> typing.Tuple[str, str]:

        sent_emoji = self.config["sent_emoji"]
        blocked_emoji = self.config["blocked_emoji"]

        if sent_emoji != "disable":
            try:
                sent_emoji = await self.convert_emoji(sent_emoji)
            except commands.BadArgument:
                logger.warning("Removed sent emoji (%s).", sent_emoji)
                sent_emoji = self.config.remove("sent_emoji")
                await self.config.update()

        if blocked_emoji != "disable":
            try:
                blocked_emoji = await self.convert_emoji(blocked_emoji)
            except commands.BadArgument:
                logger.warning("Removed blocked emoji (%s).", blocked_emoji)
                blocked_emoji = self.config.remove("blocked_emoji")
                await self.config.update()

        return sent_emoji, blocked_emoji

    async def _process_blocked(
        self, message: discord.Message
    ) -> typing.Tuple[bool, str]:
        sent_emoji, blocked_emoji = await self.retrieve_emoji()

        if str(message.author.id) in self.blocked_whitelisted_users:
            if str(message.author.id) in self.blocked_users:
                self.blocked_users.pop(str(message.author.id))
                await self.config.update()

            return False, sent_emoji

        now = datetime.utcnow()

        account_age = self.config.get("account_age")
        guild_age = self.config.get("guild_age")

        if account_age is None:
            account_age = isodate.Duration()
        if guild_age is None:
            guild_age = isodate.Duration()

        reason = self.blocked_users.get(str(message.author.id)) or ""
        min_guild_age = min_account_age = now

        try:
            min_account_age = message.author.created_at + account_age
        except ValueError:
            logger.warning("Error with 'account_age'.", exc_info=True)
            self.config.remove("account_age")

        try:
            joined_at = getattr(message.author, "joined_at", None)
            if joined_at is not None:
                min_guild_age = joined_at + guild_age
        except ValueError:
            logger.warning("Error with 'guild_age'.", exc_info=True)
            self.config.remove("guild_age")

        if min_account_age > now:
            # User account has not reached the required time
            reaction = blocked_emoji
            changed = False
            delta = human_timedelta(min_account_age)
            logger.debug("Blocked due to account age, user %s.", message.author.name)

            if str(message.author.id) not in self.blocked_users:
                new_reason = (
                    f"System Message: New Account. Required to wait for {delta}."
                )
                self.blocked_users[str(message.author.id)] = new_reason
                changed = True

            if reason.startswith("System Message: New Account.") or changed:
                await message.channel.send(
                    embed=discord.Embed(
                        title="Message not sent!",
                        description=f"Your must wait for {delta} "
                        f"before you can contact me.",
                        color=self.error_color,
                    )
                )

        elif min_guild_age > now:
            # User has not stayed in the guild for long enough
            reaction = blocked_emoji
            changed = False
            delta = human_timedelta(min_guild_age)
            logger.debug("Blocked due to guild age, user %s.", message.author.name)

            if str(message.author.id) not in self.blocked_users:
                new_reason = (
                    f"System Message: Recently Joined. Required to wait for {delta}."
                )
                self.blocked_users[str(message.author.id)] = new_reason
                changed = True

            if reason.startswith("System Message: Recently Joined.") or changed:
                await message.channel.send(
                    embed=discord.Embed(
                        title="Message not sent!",
                        description=f"Your must wait for {delta} "
                        f"before you can contact me.",
                        color=self.error_color,
                    )
                )

        elif str(message.author.id) in self.blocked_users:
            if reason.startswith("System Message: New Account.") or reason.startswith(
                "System Message: Recently Joined."
            ):
                # Met the age limit already, otherwise it would've been caught by the previous if's
                reaction = sent_emoji
                logger.debug(
                    "No longer internally blocked, user %s.", message.author.name
                )
                self.blocked_users.pop(str(message.author.id))
            else:
                reaction = blocked_emoji
                # etc "blah blah blah... until 2019-10-14T21:12:45.559948."
                end_time = re.search(r"until ([^`]+?)\.$", reason)
                if end_time is None:
                    # backwards compat
                    end_time = re.search(r"%([^%]+?)%", reason)
                    if end_time is not None:
                        logger.warning(
                            r"Deprecated time message for user %s, block and unblock again to update.",
                            message.author,
                        )

                if end_time is not None:
                    after = (
                        datetime.fromisoformat(end_time.group(1)) - now
                    ).total_seconds()
                    if after <= 0:
                        # No longer blocked
                        reaction = sent_emoji
                        self.blocked_users.pop(str(message.author.id))
                        logger.debug("No longer blocked, user %s.", message.author.name)
                    else:
                        logger.debug("User blocked, user %s.", message.author.name)
                else:
                    logger.debug("User blocked, user %s.", message.author.name)
        else:
            reaction = sent_emoji

        await self.config.update()
        return str(message.author.id) in self.blocked_users, reaction

    @staticmethod
    async def add_reaction(msg, reaction):
        if reaction != "disable":
            try:
                await msg.add_reaction(reaction)
            except (discord.HTTPException, discord.InvalidArgument):
                logger.warning("Failed to add reaction %s.", reaction, exc_info=True)

    async def process_dm_modmail(self, message: discord.Message) -> None:
        """Processes messages sent to the bot."""
        blocked, reaction = await self._process_blocked(message)
        if blocked:
            return await self.add_reaction(message, reaction)
        thread = await self.threads.find(recipient=message.author)
        if thread is None:
            if self.config["dm_disabled"] >= 1:
                embed = discord.Embed(
                    title=self.config["disabled_new_thread_title"],
                    color=self.error_color,
                    description=self.config["disabled_new_thread_response"],
                )
                embed.set_footer(
                    text=self.config["disabled_new_thread_footer"],
                    icon_url=self.guild.icon_url,
                )
                logger.info(
                    "A new thread was blocked from %s due to disabled Modmail.",
                    message.author,
                )
                _, blocked_emoji = await self.retrieve_emoji()
                await self.add_reaction(message, blocked_emoji)
                return await message.channel.send(embed=embed)
            thread = self.threads.create(message.author)
        else:
            if self.config["dm_disabled"] == 2:
                embed = discord.Embed(
                    title=self.config["disabled_current_thread_title"],
                    color=self.error_color,
                    description=self.config["disabled_current_thread_response"],
                )
                embed.set_footer(
                    text=self.config["disabled_current_thread_footer"],
                    icon_url=self.guild.icon_url,
                )
                logger.info(
                    "A message was blocked from %s due to disabled Modmail.",
                    message.author,
                )
                _, blocked_emoji = await self.retrieve_emoji()
                await self.add_reaction(message, blocked_emoji)
                return await message.channel.send(embed=embed)

        await self.add_reaction(message, reaction)
        await thread.send(message)

    async def get_contexts(self, message, *, cls=commands.Context):
        """
        Returns all invocation contexts from the message.
        Supports getting the prefix from database as well as command aliases.
        """

        view = StringView(message.content)
        ctx = cls(prefix=self.prefix, view=view, bot=self, message=message)
        ctx.thread = await self.threads.find(channel=ctx.channel)

        if self._skip_check(message.author.id, self.user.id):
            return [ctx]

        prefixes = await self.get_prefix()

        invoked_prefix = discord.utils.find(view.skip_string, prefixes)
        if invoked_prefix is None:
            return [ctx]

        invoker = view.get_word().lower()

        # Check if there is any aliases being called.
        alias = self.aliases.get(invoker)
        if alias is not None:
            aliases = parse_alias(alias)
            if not aliases:
                logger.warning("Alias %s is invalid, removing.", invoker)
                self.aliases.pop(invoker)
            else:
                len_ = len(f"{invoked_prefix}{invoker}")
                contents = parse_alias(message.content[len_:])
                if not contents:
                    contents = [message.content[len_:]]

                ctxs = []
                for alias, content in zip_longest(aliases, contents):
                    if alias is None:
                        break
                    ctx = cls(prefix=self.prefix, view=view, bot=self, message=message)
                    ctx.thread = await self.threads.find(channel=ctx.channel)

                    if content is not None:
                        view = StringView(f"{alias} {content.strip()}")
                    else:
                        view = StringView(alias)
                    ctx.view = view
                    ctx.invoked_with = view.get_word()
                    ctx.command = self.all_commands.get(ctx.invoked_with)
                    ctxs += [ctx]
                return ctxs

        ctx.invoked_with = invoker
        ctx.command = self.all_commands.get(invoker)
        return [ctx]

    async def get_context(self, message, *, cls=commands.Context):
        """
        Returns the invocation context from the message.
        Supports getting the prefix from database.
        """

        view = StringView(message.content)
        ctx = cls(prefix=self.prefix, view=view, bot=self, message=message)

        if self._skip_check(message.author.id, self.user.id):
            return ctx

        ctx.thread = await self.threads.find(channel=ctx.channel)

        prefixes = await self.get_prefix()

        invoked_prefix = discord.utils.find(view.skip_string, prefixes)
        if invoked_prefix is None:
            return ctx

        invoker = view.get_word().lower()

        ctx.invoked_with = invoker
        ctx.command = self.all_commands.get(invoker)

        return ctx

    async def update_perms(
        self, name: typing.Union[PermissionLevel, str], value: int, add: bool = True
    ) -> None:
        value = int(value)
        if isinstance(name, PermissionLevel):
            permissions = self.config["level_permissions"]
            name = name.name
        else:
            permissions = self.config["command_permissions"]
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
        logger.info("Updating permissions for %s, %s (add=%s).", name, value, add)
        await self.config.update()

    async def on_message(self, message):
        await self.wait_for_connected()
        if message.type == discord.MessageType.pins_add and message.author == self.user:
            await message.delete()
        await self.process_commands(message)

    async def process_commands(self, message):
        if message.author.bot:
            return

        if isinstance(message.channel, discord.DMChannel):
            return await self.process_dm_modmail(message)

        if message.content.startswith(self.prefix):
            cmd = message.content[len(self.prefix) :].strip()

            # Process snippets
            if cmd in self.snippets:
                thread = await self.threads.find(channel=message.channel)
                snippet = self.snippets[cmd]
                if thread:
                    snippet = self.formatter.format(snippet, recipient=thread.recipient)
                message.content = f"{self.prefix}reply {snippet}"

        ctxs = await self.get_contexts(message)
        for ctx in ctxs:
            if ctx.command:
                if not any(
                    1
                    for check in ctx.command.checks
                    if hasattr(check, "permission_level")
                ):
                    logger.debug(
                        "Command %s has no permissions check, adding invalid level.",
                        ctx.command.qualified_name,
                    )
                    checks.has_permissions(PermissionLevel.INVALID)(ctx.command)

                await self.invoke(ctx)
                continue

            thread = await self.threads.find(channel=ctx.channel)
            if thread is not None:
                if self.config.get("anon_reply_without_command"):
                    await thread.reply(message, anonymous=True)
                elif self.config.get("reply_without_command"):
                    await thread.reply(message)
                else:
                    await self.api.append_log(message, type_="internal")
            elif ctx.invoked_with:
                exc = commands.CommandNotFound(
                    'Command "{}" is not found'.format(ctx.invoked_with)
                )
                self.dispatch("command_error", ctx, exc)

    async def on_typing(self, channel, user, _):
        await self.wait_for_connected()

        if user.bot:
            return

        async def _void(*_args, **_kwargs):
            pass

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
            if thread is not None and thread.recipient:
                if (
                    await self._process_blocked(
                        SimpleNamespace(
                            author=thread.recipient, channel=SimpleNamespace(send=_void)
                        )
                    )
                )[0]:
                    return
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

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden):
            return

        reaction = payload.emoji

        close_emoji = await self.convert_emoji(self.config["close_emoji"])

        if isinstance(channel, discord.DMChannel):
            if str(reaction) == str(close_emoji):  # closing thread
                if not self.config.get("recipient_thread_close"):
                    return
                thread = await self.threads.find(recipient=user)
                ts = message.embeds[0].timestamp if message.embeds else None
                if thread and ts == thread.channel.created_at:
                    # the reacted message is the corresponding thread creation embed
                    await thread.close(closer=user)
        else:
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

        if isinstance(channel, discord.CategoryChannel):
            if self.main_category.id == channel.id:
                logger.debug("Main category was deleted.")
                self.config.remove("main_category_id")
                await self.config.update()
            return

        if not isinstance(channel, discord.TextChannel):
            return

        if self.log_channel is None or self.log_channel.id == channel.id:
            logger.info("Log channel deleted.")
            self.config.remove("log_channel_id")
            await self.config.update()
            return

        thread = await self.threads.find(channel=channel)
        if thread:
            logger.debug("Manually closed channel %s.", channel.name)
            await thread.close(closer=mod, silent=True, delete_channel=False)

    async def on_member_remove(self, member):
        if member.guild != self.guild:
            return
        thread = await self.threads.find(recipient=member)
        if thread:
            embed = discord.Embed(
                description="The recipient has left the server.", color=self.error_color
            )
            await thread.channel.send(embed=embed)

    async def on_member_join(self, member):
        if member.guild != self.guild:
            return
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
        logger.error("Ignoring exception in %s.", event_method)
        logger.error("Unexpected exception:", exc_info=sys.exc_info())

    async def on_command_error(self, context, exception):
        if isinstance(exception, commands.BadUnionArgument):
            msg = "Could not find the specified " + human_join(
                [c.__name__ for c in exception.converters]
            )
            await context.trigger_typing()
            await context.send(
                embed=discord.Embed(color=self.error_color, description=msg)
            )

        elif isinstance(exception, commands.BadArgument):
            await context.trigger_typing()
            await context.send(
                embed=discord.Embed(color=self.error_color, description=str(exception))
            )
        elif isinstance(exception, commands.CommandNotFound):
            logger.warning("CommandNotFound: %s", exception)
        elif isinstance(exception, commands.MissingRequiredArgument):
            await context.send_help(context.command)
        elif isinstance(exception, commands.CheckFailure):
            for check in context.command.checks:
                if not await check(context):
                    if hasattr(check, "fail_msg"):
                        await context.send(
                            embed=discord.Embed(
                                color=self.error_color, description=check.fail_msg
                            )
                        )
                    if hasattr(check, "permission_level"):
                        corrected_permission_level = self.command_perm(
                            context.command.qualified_name
                        )
                        logger.warning(
                            "User %s does not have permission to use this command: `%s` (%s).",
                            context.author.name,
                            context.command.qualified_name,
                            corrected_permission_level.name,
                        )
            logger.warning("CheckFailure: %s", exception)
        else:
            logger.error("Unexpected exception:", exc_info=exception)

    async def validate_database_connection(self):
        try:
            await self.db.command("buildinfo")
        except Exception as exc:
            logger.critical("Something went wrong while connecting to the database.")
            message = f"{type(exc).__name__}: {str(exc)}"
            logger.critical(message)

            if "ServerSelectionTimeoutError" in message:
                logger.critical(
                    "This may have been caused by not whitelisting "
                    "IPs correctly. Make sure to whitelist all "
                    "IPs (0.0.0.0/0) https://i.imgur.com/mILuQ5U.png"
                )

            if "OperationFailure" in message:
                logger.critical(
                    "This is due to having invalid credentials in your MONGO_URI. "
                    "Remember you need to substitute `<password>` with your actual password."
                )
                logger.critical(
                    "Be sure to URL encode your username and password (not the entire URL!!), "
                    "https://www.urlencoder.io/, if this issue persists, try changing your username and password "
                    "to only include alphanumeric characters, no symbols."
                    ""
                )
            raise
        else:
            logger.debug("Successfully connected to the database.")
        logger.line("debug")

    async def post_metadata(self):
        owner = (await self.application_info()).owner
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
            "version": str(self.version),
            "selfhosted": True,
            "last_updated": str(datetime.utcnow()),
        }

        async with self.session.post("https://api.logviewer.tech/metadata", json=data):
            logger.debug("Uploading metadata to Modmail server.")

    async def before_post_metadata(self):
        await self.wait_for_connected()
        logger.debug("Starting metadata loop.")
        logger.line("debug")
        if not self.guild:
            self.metadata_loop.cancel()


if __name__ == "__main__":
    try:
        # noinspection PyUnresolvedReferences
        import uvloop

        logger.debug("Setting up with uvloop.")
        uvloop.install()
    except ImportError:
        pass

    bot = ModmailBot()
    bot.run()
