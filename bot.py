__version__ = "4.0.2"


import asyncio
import copy
import hashlib
import logging
import os
import re
import string
import struct
import sys
import platform
import typing
from datetime import datetime, timezone
from subprocess import PIPE
from types import SimpleNamespace

import discord
import isodate
from aiohttp import ClientSession, ClientResponseError
from discord.ext import commands, tasks
from discord.ext.commands.view import StringView
from emoji import UNICODE_EMOJI
from pkg_resources import parse_version


try:
    # noinspection PyUnresolvedReferences
    from colorama import init

    init()
except ImportError:
    pass

from core import checks
from core.changelog import Changelog
from core.clients import ApiClient, MongoDBClient, PluginDatabaseClient
from core.config import ConfigManager
from core.models import (
    DMDisabled,
    HostingMethod,
    InvalidConfigError,
    PermissionLevel,
    SafeFormatter,
    configure_logging,
    getLogger,
)
from core.thread import ThreadManager
from core.time import human_timedelta
from core.utils import extract_block_timestamp, normalize_alias, parse_alias, truncate, tryint

logger = getLogger(__name__)


temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
if not os.path.exists(temp_dir):
    os.mkdir(temp_dir)

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except AttributeError:
        logger.error("Failed to use WindowsProactorEventLoopPolicy.", exc_info=True)


class ModmailBot(commands.Bot):
    def __init__(self):
        self.config = ConfigManager(self)
        self.config.populate_cache()

        intents = discord.Intents.all()
        if not self.config["enable_presence_intent"]:
            intents.presences = False

        super().__init__(command_prefix=None, intents=intents)  # implemented in `get_prefix`
        self.session = None
        self._api = None
        self.formatter = SafeFormatter()
        self.loaded_cogs = ["cogs.modmail", "cogs.plugins", "cogs.utility"]
        self._connected = None
        self.start_time = discord.utils.utcnow()
        self._started = False

        self.threads = ThreadManager(self)

        self.log_file_name = os.path.join(temp_dir, f"{self.token.split('.')[0]}.log")
        self._configure_logging()

        self.plugin_db = PluginDatabaseClient(self)  # Deprecated
        self.startup()

    def get_guild_icon(self, guild: typing.Optional[discord.Guild]) -> str:
        if guild is None:
            guild = self.guild
        if guild.icon is None:
            return "https://cdn.discordapp.com/embed/avatars/0.png"
        return guild.icon.url

    def _resolve_snippet(self, name: str) -> typing.Optional[str]:
        """
        Get actual snippet names from direct aliases to snippets.

        If the provided name is a snippet, it's returned unchanged.
        If there is an alias by this name, it is parsed to see if it
        refers only to a snippet, in which case that snippet name is
        returned.

        If no snippets were found, None is returned.
        """
        if name in self.snippets:
            return name

        try:
            (command,) = parse_alias(self.aliases[name])
        except (KeyError, ValueError):
            # There is either no alias by this name present or the
            # alias has multiple steps.
            pass
        else:
            if command in self.snippets:
                return command

    @property
    def uptime(self) -> str:
        now = discord.utils.utcnow()
        delta = now - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        fmt = "{h}h {m}m {s}s"
        if days:
            fmt = "{d}d " + fmt

        return self.formatter.format(fmt, d=days, h=hours, m=minutes, s=seconds)

    @property
    def hosting_method(self) -> HostingMethod:
        # use enums
        if ".heroku" in os.environ.get("PYTHONHOME", ""):
            return HostingMethod.HEROKU

        if os.environ.get("pm_id"):
            return HostingMethod.PM2

        if os.environ.get("INVOCATION_ID"):
            return HostingMethod.SYSTEMD

        if os.environ.get("USING_DOCKER"):
            return HostingMethod.DOCKER

        if os.environ.get("TERM"):
            return HostingMethod.SCREEN

        return HostingMethod.OTHER

    def startup(self):
        logger.line()
        logger.info("┌┬┐┌─┐┌┬┐┌┬┐┌─┐┬┬")
        logger.info("││││ │ │││││├─┤││")
        logger.info("┴ ┴└─┘─┴┘┴ ┴┴ ┴┴┴─┘")
        logger.info("v%s", __version__)
        logger.info("Authors: kyb3r, fourjr, Taaku18")
        logger.line()
        logger.info("discord.py: v%s", discord.__version__)
        logger.line()

    async def load_extensions(self):
        for cog in self.loaded_cogs:
            if cog in self.extensions:
                continue
            logger.debug("Loading %s.", cog)
            try:
                await self.load_extension(cog)
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
    def api(self) -> ApiClient:
        if self._api is None:
            if self.config["database_type"].lower() == "mongodb":
                self._api = MongoDBClient(self)
            else:
                logger.critical("Invalid database type.")
                raise RuntimeError
        return self._api

    @property
    def db(self):
        # deprecated
        return self.api.db

    async def get_prefix(self, message=None):
        return [self.prefix, f"<@{self.user.id}> ", f"<@!{self.user.id}> "]

    def run(self):
        async def runner():
            async with self:
                self._connected = asyncio.Event()
                self.session = ClientSession(loop=self.loop)

                if self.config["enable_presence_intent"]:
                    logger.info("Starting bot with presence intent.")
                else:
                    logger.info("Starting bot without presence intent.")

                try:
                    await self.start(self.token)
                except discord.PrivilegedIntentsRequired:
                    logger.critical(
                        "Privileged intents are not explicitly granted in the discord developers dashboard."
                    )
                except discord.LoginFailure:
                    logger.critical("Invalid token")
                except Exception:
                    logger.critical("Fatal exception", exc_info=True)
                finally:
                    if self.session:
                        await self.session.close()
                    if not self.is_closed():
                        await self.close()

        async def _cancel_tasks():
            async with self:
                task_retriever = asyncio.all_tasks
                loop = self.loop
                tasks = {t for t in task_retriever() if not t.done() and t.get_coro() != cancel_tasks_coro}

                if not tasks:
                    return

                logger.info("Cleaning up after %d tasks.", len(tasks))
                for task in tasks:
                    task.cancel()

                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info("All tasks finished cancelling.")

                for task in tasks:
                    try:
                        if task.exception() is not None:
                            loop.call_exception_handler(
                                {
                                    "message": "Unhandled exception during Client.run shutdown.",
                                    "exception": task.exception(),
                                    "task": task,
                                }
                            )
                    except (asyncio.InvalidStateError, asyncio.CancelledError):
                        pass

        try:
            asyncio.run(runner(), debug=bool(os.getenv("DEBUG_ASYNCIO")))
        except (KeyboardInterrupt, SystemExit):
            logger.info("Received signal to terminate bot and event loop.")
        finally:
            logger.info("Cleaning up tasks.")

            try:
                cancel_tasks_coro = _cancel_tasks()
                asyncio.run(cancel_tasks_coro)
            finally:
                logger.info("Closing the event loop.")

    @property
    def bot_owner_ids(self):
        owner_ids = self.config["owners"]
        if owner_ids is not None:
            owner_ids = set(map(int, str(owner_ids).split(",")))
        if self.owner_id is not None:
            owner_ids.add(self.owner_id)
        permissions = self.config["level_permissions"].get(PermissionLevel.OWNER.name, [])
        for perm in permissions:
            owner_ids.add(int(perm))
        return owner_ids

    async def is_owner(self, user: discord.User) -> bool:
        if user.id in self.bot_owner_ids:
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
                logger.warning("No log channel set, setting #%s to be the log channel.", channel.name)
                return channel
            except IndexError:
                pass
        logger.warning(
            "No log channel set, set one with `%ssetup` or `%sconfig set log_channel_id <id>`.",
            self.prefix,
            self.prefix,
        )
        return None

    @property
    def mention_channel(self):
        channel_id = self.config["mention_channel_id"]
        if channel_id is not None:
            try:
                channel = self.get_channel(int(channel_id))
                if channel is not None:
                    return channel
            except ValueError:
                pass
            logger.debug("MENTION_CHANNEL_ID was invalid, removed.")
            self.config.remove("mention_channel_id")

        return self.log_channel

    @property
    def update_channel(self):
        channel_id = self.config["update_channel_id"]
        if channel_id is not None:
            try:
                channel = self.get_channel(int(channel_id))
                if channel is not None:
                    return channel
            except ValueError:
                pass
            logger.debug("UPDATE_CHANNEL_ID was invalid, removed.")
            self.config.remove("update_channel_id")

        return self.log_channel

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
    def auto_triggers(self) -> typing.Dict[str, str]:
        return self.config["auto_triggers"]

    @property
    def token(self) -> str:
        token = self.config["token"]
        if token is None:
            logger.critical("TOKEN must be set, set this as bot token found on the Discord Developer Portal.")
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
                    cat = discord.utils.get(self.modmail_guild.categories, id=int(category_id))
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
    def blocked_roles(self) -> typing.Dict[str, str]:
        return self.config["blocked_roles"]

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
                logger.warning("Invalid override_command_level for command %s.", command_name)
                self.config["override_command_level"].pop(command_name)

        command = self.get_command(command_name)
        if command is None:
            logger.debug("Command %s not found.", command_name)
            return PermissionLevel.INVALID
        level = next(
            (check.permission_level for check in command.checks if hasattr(check, "permission_level")),
            None,
        )
        if level is None:
            logger.debug("Command %s does not have a permission level.", command_name)
            return PermissionLevel.INVALID
        return level

    async def on_connect(self):
        try:
            await self.api.validate_database_connection()
        except Exception:
            logger.debug("Logging out due to failed database connection.")
            return await self.close()

        logger.debug("Connected to gateway.")
        await self.config.refresh()
        await self.api.setup_indexes()
        await self.load_extensions()
        self._connected.set()

    async def on_ready(self):
        """Bot startup, sets uptime."""

        # Wait until config cache is populated with stuff from db and on_connect ran
        await self.wait_for_connected()

        if self.guild is None:
            logger.error("Logging out due to invalid GUILD_ID.")
            return await self.close()

        if self._started:
            # Bot has started before
            logger.line()
            logger.warning("Bot restarted due to internal discord reloading.")
            logger.line()
            return

        logger.line()
        logger.debug("Client ready.")
        logger.info("Logged in as: %s", self.user)
        logger.info("Bot ID: %s", self.user.id)
        owners = ", ".join(
            getattr(self.get_user(owner_id), "name", str(owner_id)) for owner_id in self.bot_owner_ids
        )
        logger.info("Owners: %s", owners)
        logger.info("Prefix: %s", self.prefix)
        logger.info("Guild Name: %s", self.guild.name)
        logger.info("Guild ID: %s", self.guild.id)
        if self.using_multiple_server_setup:
            logger.info("Receiving guild ID: %s", self.modmail_guild.id)
        logger.line()

        if "dev" in __version__:
            logger.warning(
                "You are running a developmental version. This should not be used in production. (v%s)",
                __version__,
            )
            logger.line()

        await self.threads.populate_cache()

        # closures
        closures = self.config["closures"]
        logger.info("There are %d thread(s) pending to be closed.", len(closures))
        logger.line()

        for recipient_id, items in tuple(closures.items()):
            after = (
                datetime.fromisoformat(items["time"]).astimezone(timezone.utc) - discord.utils.utcnow()
            ).total_seconds()
            if after <= 0:
                logger.debug("Closing thread for recipient %s.", recipient_id)
                after = 0
            else:
                logger.debug("Thread for recipient %s will be closed after %s seconds.", recipient_id, after)

            thread = await self.threads.find(recipient_id=int(recipient_id))

            if not thread:
                # If the channel is deleted
                logger.debug("Failed to close thread for recipient %s.", recipient_id)
                self.config["closures"].pop(recipient_id)
                await self.config.update()
                continue

            await thread.close(
                closer=await self.get_or_fetch_user(items["closer_id"]),
                after=after,
                silent=items["silent"],
                delete_channel=items["delete_channel"],
                message=items["message"],
                auto_close=items.get("auto_close", False),
            )

        for log in await self.api.get_open_logs():
            if self.get_channel(int(log["channel_id"])) is None:
                logger.debug("Unable to resolve thread with channel %s.", log["channel_id"])
                log_data = await self.api.post_log(
                    log["channel_id"],
                    {
                        "open": False,
                        "title": None,
                        "closed_at": str(discord.utils.utcnow()),
                        "close_message": "Channel has been deleted, no closer found.",
                        "closer": {
                            "id": str(self.user.id),
                            "name": self.user.name,
                            "discriminator": self.user.discriminator,
                            "avatar_url": self.user.display_avatar.url,
                            "mod": True,
                        },
                    },
                )
                if log_data:
                    logger.debug("Successfully closed thread with channel %s.", log["channel_id"])
                else:
                    logger.debug("Failed to close thread with channel %s, skipping.", log["channel_id"])

        other_guilds = [guild for guild in self.guilds if guild not in {self.guild, self.modmail_guild}]
        if any(other_guilds):
            logger.warning(
                "The bot is in more servers other than the main and staff server. "
                "This may cause data compromise (%s).",
                ", ".join(str(guild.name) for guild in other_guilds),
            )
            logger.warning("If the external servers are valid, you may ignore this message.")

        self.post_metadata.start()
        self.autoupdate.start()
        self._started = True

    async def convert_emoji(self, name: str) -> str:
        ctx = SimpleNamespace(bot=self, guild=self.modmail_guild)
        converter = commands.EmojiConverter()

        if name not in UNICODE_EMOJI["en"]:
            try:
                name = await converter.convert(ctx, name.strip(":"))
            except commands.BadArgument as e:
                logger.warning("%s is not a valid emoji. %s.", name, e)
                raise
        return name

    async def get_or_fetch_user(self, id: int) -> discord.User:
        """
        Retrieve a User based on their ID.

        This tries getting the user from the cache and falls back to making
        an API call if they're not found in the cache.
        """
        return self.get_user(id) or await self.fetch_user(id)

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

    def check_account_age(self, author: discord.Member) -> bool:
        account_age = self.config.get("account_age")
        now = discord.utils.utcnow()

        try:
            min_account_age = author.created_at + account_age
        except ValueError:
            logger.warning("Error with 'account_age'.", exc_info=True)
            min_account_age = author.created_at + self.config.remove("account_age")

        if min_account_age > now:
            # User account has not reached the required time
            delta = human_timedelta(min_account_age)
            logger.debug("Blocked due to account age, user %s.", author.name)

            if str(author.id) not in self.blocked_users:
                new_reason = f"System Message: New Account. User can try again {delta}."
                self.blocked_users[str(author.id)] = new_reason

            return False
        return True

    def check_guild_age(self, author: discord.Member) -> bool:
        guild_age = self.config.get("guild_age")
        now = discord.utils.utcnow()

        if not hasattr(author, "joined_at"):
            logger.warning("Not in guild, cannot verify guild_age, %s.", author.name)
            return True

        try:
            min_guild_age = author.joined_at + guild_age
        except ValueError:
            logger.warning("Error with 'guild_age'.", exc_info=True)
            min_guild_age = author.joined_at + self.config.remove("guild_age")

        if min_guild_age > now:
            # User has not stayed in the guild for long enough
            delta = human_timedelta(min_guild_age)
            logger.debug("Blocked due to guild age, user %s.", author.name)

            if str(author.id) not in self.blocked_users:
                new_reason = f"System Message: Recently Joined. User can try again {delta}."
                self.blocked_users[str(author.id)] = new_reason

            return False
        return True

    def check_manual_blocked_roles(self, author: discord.Member) -> bool:
        if isinstance(author, discord.Member):
            for r in author.roles:
                if str(r.id) in self.blocked_roles:

                    blocked_reason = self.blocked_roles.get(str(r.id)) or ""

                    try:
                        end_time, after = extract_block_timestamp(blocked_reason, author.id)
                    except ValueError:
                        return False

                    if end_time is not None:
                        if after <= 0:
                            # No longer blocked
                            self.blocked_roles.pop(str(r.id))
                            logger.debug("No longer blocked, role %s.", r.name)
                            return True
                    logger.debug("User blocked, role %s.", r.name)
                    return False

        return True

    def check_manual_blocked(self, author: discord.Member) -> bool:
        if str(author.id) not in self.blocked_users:
            return True

        blocked_reason = self.blocked_users.get(str(author.id)) or ""

        if blocked_reason.startswith("System Message:"):
            # Met the limits already, otherwise it would've been caught by the previous checks
            logger.debug("No longer internally blocked, user %s.", author.name)
            self.blocked_users.pop(str(author.id))
            return True

        try:
            end_time, after = extract_block_timestamp(blocked_reason, author.id)
        except ValueError:
            return False

        if end_time is not None:
            if after <= 0:
                # No longer blocked
                self.blocked_users.pop(str(author.id))
                logger.debug("No longer blocked, user %s.", author.name)
                return True
        logger.debug("User blocked, user %s.", author.name)
        return False

    async def _process_blocked(self, message):
        _, blocked_emoji = await self.retrieve_emoji()
        if await self.is_blocked(message.author, channel=message.channel, send_message=True):
            await self.add_reaction(message, blocked_emoji)
            return True
        return False

    async def is_blocked(
        self,
        author: discord.User,
        *,
        channel: discord.TextChannel = None,
        send_message: bool = False,
    ) -> bool:

        member = self.guild.get_member(author.id)
        if member is None:
            # try to find in other guilds
            for g in self.guilds:
                member = g.get_member(author.id)
                if member:
                    break

            if member is None:
                logger.debug("User not in guild, %s.", author.id)

        if member is not None:
            author = member

        if str(author.id) in self.blocked_whitelisted_users:
            if str(author.id) in self.blocked_users:
                self.blocked_users.pop(str(author.id))
                await self.config.update()
            return False

        blocked_reason = self.blocked_users.get(str(author.id)) or ""

        if not self.check_account_age(author) or not self.check_guild_age(author):
            new_reason = self.blocked_users.get(str(author.id))
            if new_reason != blocked_reason:
                if send_message:
                    await channel.send(
                        embed=discord.Embed(
                            title="Message not sent!",
                            description=new_reason,
                            color=self.error_color,
                        )
                    )
            return True

        if not self.check_manual_blocked(author):
            return True

        if not self.check_manual_blocked_roles(author):
            return True

        await self.config.update()
        return False

    async def get_thread_cooldown(self, author: discord.Member):
        thread_cooldown = self.config.get("thread_cooldown")
        now = discord.utils.utcnow()

        if thread_cooldown == isodate.Duration():
            return

        last_log = await self.api.get_latest_user_logs(author.id)

        if last_log is None:
            logger.debug("Last thread wasn't found, %s.", author.name)
            return

        last_log_closed_at = last_log.get("closed_at")

        if not last_log_closed_at:
            logger.debug("Last thread was not closed, %s.", author.name)
            return

        try:
            cooldown = datetime.fromisoformat(last_log_closed_at).astimezone(timezone.utc) + thread_cooldown
        except ValueError:
            logger.warning("Error with 'thread_cooldown'.", exc_info=True)
            cooldown = datetime.fromisoformat(last_log_closed_at).astimezone(
                timezone.utc
            ) + self.config.remove("thread_cooldown")

        if cooldown > now:
            # User messaged before thread cooldown ended
            delta = human_timedelta(cooldown)
            logger.debug("Blocked due to thread cooldown, user %s.", author.name)
            return delta
        return

    @staticmethod
    async def add_reaction(
        msg, reaction: typing.Union[discord.Emoji, discord.Reaction, discord.PartialEmoji, str]
    ) -> bool:
        if reaction != "disable":
            try:
                await msg.add_reaction(reaction)
            except (discord.HTTPException, TypeError) as e:
                logger.warning("Failed to add reaction %s: %s.", reaction, e)
                return False
        return True

    async def process_dm_modmail(self, message: discord.Message) -> None:
        """Processes messages sent to the bot."""
        blocked = await self._process_blocked(message)
        if blocked:
            return
        sent_emoji, blocked_emoji = await self.retrieve_emoji()

        if message.type != discord.MessageType.default:
            return

        thread = await self.threads.find(recipient=message.author)
        if thread is None:
            delta = await self.get_thread_cooldown(message.author)
            if delta:
                await message.channel.send(
                    embed=discord.Embed(
                        title=self.config["cooldown_thread_title"],
                        description=self.config["cooldown_thread_response"].format(delta=delta),
                        color=self.error_color,
                    )
                )
                return

            if self.config["dm_disabled"] in (DMDisabled.NEW_THREADS, DMDisabled.ALL_THREADS):
                embed = discord.Embed(
                    title=self.config["disabled_new_thread_title"],
                    color=self.error_color,
                    description=self.config["disabled_new_thread_response"],
                )
                embed.set_footer(
                    text=self.config["disabled_new_thread_footer"],
                    icon_url=self.get_guild_icon(guild=message.guild),
                )
                logger.info("A new thread was blocked from %s due to disabled Modmail.", message.author)
                await self.add_reaction(message, blocked_emoji)
                return await message.channel.send(embed=embed)

            thread = await self.threads.create(message.author, message=message)
        else:
            if self.config["dm_disabled"] == DMDisabled.ALL_THREADS:
                embed = discord.Embed(
                    title=self.config["disabled_current_thread_title"],
                    color=self.error_color,
                    description=self.config["disabled_current_thread_response"],
                )
                embed.set_footer(
                    text=self.config["disabled_current_thread_footer"],
                    icon_url=self.get_guild_icon(guild=message.guild),
                )
                logger.info("A message was blocked from %s due to disabled Modmail.", message.author)
                await self.add_reaction(message, blocked_emoji)
                return await message.channel.send(embed=embed)

        if not thread.cancelled:
            try:
                await thread.send(message)
            except Exception:
                logger.error("Failed to send message:", exc_info=True)
                await self.add_reaction(message, blocked_emoji)
            else:
                for user in thread.recipients:
                    # send to all other recipients
                    if user != message.author:
                        try:
                            await thread.send(message, user)
                        except Exception:
                            # silently ignore
                            logger.error("Failed to send message:", exc_info=True)

                await self.add_reaction(message, sent_emoji)
                self.dispatch("thread_reply", thread, False, message, False, False)

    def _get_snippet_command(self) -> commands.Command:
        """Get the correct reply command based on the snippet config"""
        modifiers = "f"
        if self.config["plain_snippets"]:
            modifiers += "p"
        if self.config["anonymous_snippets"]:
            modifiers += "a"

        return self.get_command(f"{modifiers}reply")

    async def get_contexts(self, message, *, cls=commands.Context):
        """
        Returns all invocation contexts from the message.
        Supports getting the prefix from database as well as command aliases.
        """

        view = StringView(message.content)
        ctx = cls(prefix=self.prefix, view=view, bot=self, message=message)
        thread = await self.threads.find(channel=ctx.channel)

        if message.author.id == self.user.id:  # type: ignore
            return [ctx]

        prefixes = await self.get_prefix()

        invoked_prefix = discord.utils.find(view.skip_string, prefixes)
        if invoked_prefix is None:
            return [ctx]

        invoker = view.get_word().lower()

        # Check if a snippet is being called.
        # This needs to be done before checking for aliases since
        # snippets can have multiple words.
        try:
            # Use removeprefix once PY3.9+
            snippet_text = self.snippets[message.content[len(invoked_prefix) :]]
        except KeyError:
            snippet_text = None

        # Check if there is any aliases being called.
        alias = self.aliases.get(invoker)
        if alias is not None and snippet_text is None:
            ctxs = []
            aliases = normalize_alias(alias, message.content[len(f"{invoked_prefix}{invoker}") :])
            if not aliases:
                logger.warning("Alias %s is invalid, removing.", invoker)
                self.aliases.pop(invoker)

            for alias in aliases:
                command = None
                try:
                    snippet_text = self.snippets[alias]
                except KeyError:
                    command_invocation_text = alias
                else:
                    command = self._get_snippet_command()
                    command_invocation_text = f"{invoked_prefix}{command} {snippet_text}"
                view = StringView(invoked_prefix + command_invocation_text)
                ctx_ = cls(prefix=self.prefix, view=view, bot=self, message=message)
                ctx_.thread = thread
                discord.utils.find(view.skip_string, prefixes)
                ctx_.invoked_with = view.get_word().lower()
                ctx_.command = command or self.all_commands.get(ctx_.invoked_with)
                ctxs += [ctx_]
            return ctxs

        ctx.thread = thread

        if snippet_text is not None:
            # Process snippets
            ctx.command = self._get_snippet_command()
            reply_view = StringView(f"{invoked_prefix}{ctx.command} {snippet_text}")
            discord.utils.find(reply_view.skip_string, prefixes)
            ctx.invoked_with = reply_view.get_word().lower()
            ctx.view = reply_view
        else:
            ctx.command = self.all_commands.get(invoker)
            ctx.invoked_with = invoker

        return [ctx]

    async def trigger_auto_triggers(self, message, channel, *, cls=commands.Context):
        message.author = self.modmail_guild.me
        message.channel = channel
        message.guild = channel.guild

        view = StringView(message.content)
        ctx = cls(prefix=self.prefix, view=view, bot=self, message=message)
        thread = await self.threads.find(channel=ctx.channel)

        invoked_prefix = self.prefix
        invoker = None

        if self.config.get("use_regex_autotrigger"):
            trigger = next(filter(lambda x: re.search(x, message.content), self.auto_triggers.keys()))
            if trigger:
                invoker = re.search(trigger, message.content).group(0)
        else:
            trigger = next(filter(lambda x: x.lower() in message.content.lower(), self.auto_triggers.keys()))
            if trigger:
                invoker = trigger.lower()

        alias = self.auto_triggers[trigger]

        ctxs = []

        if alias is not None:
            ctxs = []
            aliases = normalize_alias(alias)
            if not aliases:
                logger.warning("Alias %s is invalid as called in autotrigger.", invoker)

        message.author = thread.recipient  # Allow for get_contexts to work

        for alias in aliases:
            message.content = invoked_prefix + alias
            ctxs += await self.get_contexts(message)

        message.author = self.modmail_guild.me  # Fix message so commands execute properly

        for ctx in ctxs:
            if ctx.command:
                old_checks = copy.copy(ctx.command.checks)
                ctx.command.checks = [checks.has_permissions(PermissionLevel.INVALID)]

                await self.invoke(ctx)

                ctx.command.checks = old_checks
                continue

    async def get_context(self, message, *, cls=commands.Context):
        """
        Returns the invocation context from the message.
        Supports getting the prefix from database.
        """

        view = StringView(message.content)
        ctx = cls(prefix=self.prefix, view=view, bot=self, message=message)

        if message.author.id == self.user.id:
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
        if value != -1:
            value = str(value)
        if isinstance(name, PermissionLevel):
            level = True
            permissions = self.config["level_permissions"]
            name = name.name
        else:
            level = False
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

        if level:
            self.config["level_permissions"] = permissions
        else:
            self.config["command_permissions"] = permissions
        logger.info("Updating permissions for %s, %s (add=%s).", name, value, add)
        await self.config.update()

    async def on_message(self, message):
        await self.wait_for_connected()
        if message.type == discord.MessageType.pins_add and message.author == self.user:
            await message.delete()

        if (
            (f"<@{self.user.id}" in message.content or f"<@!{self.user.id}" in message.content)
            and self.config["alert_on_mention"]
            and not message.author.bot
        ):
            em = discord.Embed(
                title="Bot mention",
                description=f"[Jump URL]({message.jump_url})\n{truncate(message.content, 50)}",
                color=self.main_color,
            )
            if self.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()

            if not self.config["silent_alert_on_mention"]:
                content = self.config["mention"]
            else:
                content = ""
            await self.mention_channel.send(content=content, embed=em)

        await self.process_commands(message)

    async def process_commands(self, message):
        if message.author.bot:
            return

        if isinstance(message.channel, discord.DMChannel):
            return await self.process_dm_modmail(message)

        ctxs = await self.get_contexts(message)
        for ctx in ctxs:
            if ctx.command:
                if not any(1 for check in ctx.command.checks if hasattr(check, "permission_level")):
                    logger.debug(
                        "Command %s has no permissions check, adding invalid level.",
                        ctx.command.qualified_name,
                    )
                    checks.has_permissions(PermissionLevel.INVALID)(ctx.command)

                await self.invoke(ctx)
                continue

            thread = await self.threads.find(channel=ctx.channel)
            if thread is not None:
                anonymous = False
                plain = False
                if self.config.get("anon_reply_without_command"):
                    anonymous = True
                if self.config.get("plain_reply_without_command"):
                    plain = True

                if (
                    self.config.get("reply_without_command")
                    or self.config.get("anon_reply_without_command")
                    or self.config.get("plain_reply_without_command")
                ):
                    await thread.reply(message, anonymous=anonymous, plain=plain)
                else:
                    await self.api.append_log(message, type_="internal")
            elif ctx.invoked_with:
                exc = commands.CommandNotFound('Command "{}" is not found'.format(ctx.invoked_with))
                self.dispatch("command_error", ctx, exc)

    async def on_typing(self, channel, user, _):
        await self.wait_for_connected()

        if user.bot:
            return

        if isinstance(channel, discord.DMChannel):
            if not self.config.get("user_typing"):
                return

            thread = await self.threads.find(recipient=user)

            if thread:
                await thread.channel.typing()
        else:
            if not self.config.get("mod_typing"):
                return

            thread = await self.threads.find(channel=channel)
            if thread is not None and thread.recipient:
                for user in thread.recipients:
                    if await self.is_blocked(user):
                        continue
                    await user.typing()

    async def handle_reaction_events(self, payload):
        user = self.get_user(payload.user_id)
        if user is None or user.bot:
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
            thread = await self.threads.find(recipient=user)
            if not thread:
                return
            if (
                payload.event_type == "REACTION_ADD"
                and message.embeds
                and str(reaction) == str(close_emoji)
                and self.config.get("recipient_thread_close")
            ):
                ts = message.embeds[0].timestamp
                if thread and ts == thread.channel.created_at:
                    # the reacted message is the corresponding thread creation embed
                    # closing thread
                    return await thread.close(closer=user)
            if (
                message.author == self.user
                and message.embeds
                and self.config.get("confirm_thread_creation")
                and message.embeds[0].title == self.config["confirm_thread_creation_title"]
                and message.embeds[0].description == self.config["confirm_thread_response"]
            ):
                return
            if not thread.recipient.dm_channel:
                await thread.recipient.create_dm()
            try:
                linked_messages = await thread.find_linked_message_from_dm(message, either_direction=True)
            except ValueError as e:
                logger.warning("Failed to find linked message for reactions: %s", e)
                return
        else:
            thread = await self.threads.find(channel=channel)
            if not thread:
                return
            try:
                _, *linked_messages = await thread.find_linked_messages(message.id, either_direction=True)
            except ValueError as e:
                logger.warning("Failed to find linked message for reactions: %s", e)
                return

        if self.config["transfer_reactions"] and linked_messages is not [None]:
            if payload.event_type == "REACTION_ADD":
                for msg in linked_messages:
                    await self.add_reaction(msg, reaction)
                await self.add_reaction(message, reaction)
            else:
                try:
                    for msg in linked_messages:
                        await msg.remove_reaction(reaction, self.user)
                    await message.remove_reaction(reaction, self.user)
                except (discord.HTTPException, TypeError) as e:
                    logger.warning("Failed to remove reaction: %s", e)

    async def handle_react_to_contact(self, payload):
        react_message_id = tryint(self.config.get("react_to_contact_message"))
        react_message_emoji = self.config.get("react_to_contact_emoji")
        if not all((react_message_id, react_message_emoji)) or payload.message_id != react_message_id:
            return
        if payload.emoji.is_unicode_emoji():
            emoji_fmt = payload.emoji.name
        else:
            emoji_fmt = f"<:{payload.emoji.name}:{payload.emoji.id}>"

        if emoji_fmt != react_message_emoji:
            return
        channel = self.get_channel(payload.channel_id)
        member = channel.guild.get_member(payload.user_id)
        if member.bot:
            return
        message = await channel.fetch_message(payload.message_id)
        await message.remove_reaction(payload.emoji, member)
        await message.add_reaction(emoji_fmt)  # bot adds as well

        if self.config["dm_disabled"] in (DMDisabled.NEW_THREADS, DMDisabled.ALL_THREADS):
            embed = discord.Embed(
                title=self.config["disabled_new_thread_title"],
                color=self.error_color,
                description=self.config["disabled_new_thread_response"],
            )
            embed.set_footer(
                text=self.config["disabled_new_thread_footer"],
                icon_url=self.get_guild_icon(guild=channel.guild),
            )
            logger.info(
                "A new thread using react to contact was blocked from %s due to disabled Modmail.",
                member,
            )
            return await member.send(embed=embed)

        ctx = await self.get_context(message)
        await ctx.invoke(self.get_command("contact"), users=[member], manual_trigger=False)

    async def on_raw_reaction_add(self, payload):
        await asyncio.gather(
            self.handle_reaction_events(payload),
            self.handle_react_to_contact(payload),
        )

    async def on_raw_reaction_remove(self, payload):
        if self.config["transfer_reactions"]:
            await self.handle_reaction_events(payload)

    async def on_guild_channel_delete(self, channel):
        if channel.guild != self.modmail_guild:
            return

        if isinstance(channel, discord.CategoryChannel):
            if self.main_category == channel:
                logger.debug("Main category was deleted.")
                self.config.remove("main_category_id")
                await self.config.update()
            return

        if not isinstance(channel, discord.TextChannel):
            return

        if self.log_channel is None or self.log_channel == channel:
            logger.info("Log channel deleted.")
            self.config.remove("log_channel_id")
            await self.config.update()
            return

        audit_logs = self.modmail_guild.audit_logs(limit=10, action=discord.AuditLogAction.channel_delete)
        found_entry = False
        async for entry in audit_logs:
            if int(entry.target.id) == channel.id:
                found_entry = True
                break

        if not found_entry:
            logger.debug("Cannot find the audit log entry for channel delete of %d.", channel.id)
            return

        mod = entry.user
        if mod == self.user:
            return

        thread = await self.threads.find(channel=channel)
        if thread and thread.channel == channel:
            logger.debug("Manually closed channel %s.", channel.name)
            await thread.close(closer=mod, silent=True, delete_channel=False)

    async def on_member_remove(self, member):
        if member.guild != self.guild:
            return
        thread = await self.threads.find(recipient=member)
        if thread:
            if self.config["close_on_leave"]:
                await thread.close(
                    closer=member.guild.me,
                    message=self.config["close_on_leave_reason"],
                    silent=True,
                )
            else:
                embed = discord.Embed(
                    description=self.config["close_on_leave_reason"], color=self.error_color
                )
                await thread.channel.send(embed=embed)

    async def on_member_join(self, member):
        if member.guild != self.guild:
            return
        thread = await self.threads.find(recipient=member)
        if thread:
            embed = discord.Embed(description="The recipient has joined the server.", color=self.mod_color)
            await thread.channel.send(embed=embed)

    async def on_message_delete(self, message):
        """Support for deleting linked messages"""

        if message.is_system():
            return

        if isinstance(message.channel, discord.DMChannel):
            if message.author == self.user:
                return
            thread = await self.threads.find(recipient=message.author)
            if not thread:
                return
            try:
                message = await thread.find_linked_message_from_dm(message, get_thread_channel=True)
            except ValueError as e:
                if str(e) != "Thread channel message not found.":
                    logger.debug("Failed to find linked message to delete: %s", e)
                return
            message = message[0]
            embed = message.embeds[0]

            if embed.footer.icon:
                icon_url = embed.footer.icon.url
            else:
                icon_url = None

            embed.set_footer(text=f"{embed.footer.text} (deleted)", icon_url=icon_url)
            await message.edit(embed=embed)
            return

        if message.author != self.user:
            return

        thread = await self.threads.find(channel=message.channel)
        if not thread:
            return

        try:
            await thread.delete_message(message, note=False)
            embed = discord.Embed(description="Successfully deleted message.", color=self.main_color)
        except ValueError as e:
            if str(e) not in {"DM message not found.", "Malformed thread message."}:
                logger.debug("Failed to find linked message to delete: %s", e)
                embed = discord.Embed(description="Failed to delete message.", color=self.error_color)
            else:
                return
        except discord.NotFound:
            return
        embed.set_footer(text=f"Message ID: {message.id} from {message.author}.")
        return await message.channel.send(embed=embed)

    async def on_bulk_message_delete(self, messages):
        await discord.utils.async_all(self.on_message_delete(msg) for msg in messages)

    async def on_message_edit(self, before, after):
        if after.author.bot:
            return
        if before.content == after.content:
            return

        if isinstance(after.channel, discord.DMChannel):
            thread = await self.threads.find(recipient=before.author)
            if not thread:
                return

            try:
                await thread.edit_dm_message(after, after.content)
            except ValueError:
                _, blocked_emoji = await self.retrieve_emoji()
                await self.add_reaction(after, blocked_emoji)
            else:
                embed = discord.Embed(description="Successfully Edited Message", color=self.main_color)
                embed.set_footer(text=f"Message ID: {after.id}")
                await after.channel.send(embed=embed)

    async def on_error(self, event_method, *args, **kwargs):
        logger.error("Ignoring exception in %s.", event_method)
        logger.error("Unexpected exception:", exc_info=sys.exc_info())

    async def on_command_error(
        self, context: commands.Context, exception: Exception, *, unhandled_by_cog: bool = False
    ) -> None:
        if not unhandled_by_cog:
            command = context.command
            if command and command.has_error_handler():
                return
            cog = context.cog
            if cog and cog.has_error_handler():
                return

        if isinstance(exception, (commands.BadArgument, commands.BadUnionArgument)):
            await context.typing()
            await context.send(embed=discord.Embed(color=self.error_color, description=str(exception)))
        elif isinstance(exception, commands.CommandNotFound):
            logger.warning("CommandNotFound: %s", exception)
        elif isinstance(exception, commands.MissingRequiredArgument):
            await context.send_help(context.command)
        elif isinstance(exception, commands.CommandOnCooldown):
            await context.send(
                embed=discord.Embed(
                    title="Command on cooldown",
                    description=f"Try again in {exception.retry_after:.2f} seconds",
                    color=self.error_color,
                )
            )
        elif isinstance(exception, commands.CheckFailure):
            for check in context.command.checks:
                if not await check(context):
                    if hasattr(check, "fail_msg"):
                        await context.send(
                            embed=discord.Embed(color=self.error_color, description=check.fail_msg)
                        )
                    if hasattr(check, "permission_level"):
                        corrected_permission_level = self.command_perm(context.command.qualified_name)
                        logger.warning(
                            "User %s does not have permission to use this command: `%s` (%s).",
                            context.author.name,
                            context.command.qualified_name,
                            corrected_permission_level.name,
                        )
            logger.warning("CheckFailure: %s", exception)
        elif isinstance(exception, commands.DisabledCommand):
            logger.info("DisabledCommand: %s is trying to run eval but it's disabled", context.author.name)
        else:
            logger.error("Unexpected exception:", exc_info=exception)

    @tasks.loop(hours=1)
    async def post_metadata(self):
        info = await self.application_info()

        delta = discord.utils.utcnow() - self.start_time
        data = {
            "bot_id": self.user.id,
            "bot_name": str(self.user),
            "avatar_url": self.user.display_avatar.url,
            "guild_id": self.guild_id,
            "guild_name": self.guild.name,
            "member_count": len(self.guild.members),
            "uptime": delta.total_seconds(),
            "latency": f"{self.ws.latency * 1000:.4f}",
            "version": str(self.version),
            "selfhosted": True,
            "last_updated": str(discord.utils.utcnow()),
        }

        if info.team is not None:
            data.update(
                {
                    "owner_name": info.team.owner.name if info.team.owner is not None else "No Owner",
                    "owner_id": info.team.owner_id,
                    "team": True,
                }
            )
        else:
            data.update({"owner_name": info.owner.name, "owner_id": info.owner.id, "team": False})

        async with self.session.post("https://api.modmail.dev/metadata", json=data):
            logger.debug("Uploading metadata to Modmail server.")

    @post_metadata.before_loop
    async def before_post_metadata(self):
        await self.wait_for_connected()
        if not self.config.get("data_collection") or not self.guild:
            self.post_metadata.cancel()
            return

        logger.debug("Starting metadata loop.")
        logger.line("debug")

    @tasks.loop(hours=1)
    async def autoupdate(self):
        changelog = await Changelog.from_url(self)
        latest = changelog.latest_version

        if self.version < parse_version(latest.version):
            error = None
            data = {}
            try:
                # update fork if gh_token exists
                data = await self.api.update_repository()
            except InvalidConfigError:
                pass
            except ClientResponseError as exc:
                error = exc
            if self.hosting_method == HostingMethod.HEROKU:
                if error is not None:
                    logger.error(f"Autoupdate failed! Status: {error.status}.")
                    logger.error(f"Error message: {error.message}")
                    self.autoupdate.cancel()
                    return

                commit_data = data.get("data")
                if not commit_data:
                    return

                logger.info("Bot has been updated.")

                if not self.config["update_notifications"]:
                    return

                embed = discord.Embed(color=self.main_color)
                message = commit_data["commit"]["message"]
                html_url = commit_data["html_url"]
                short_sha = commit_data["sha"][:6]
                user = data["user"]
                embed.add_field(
                    name="Merge Commit",
                    value=f"[`{short_sha}`]({html_url}) " f"{message} - {user['username']}",
                )
                embed.set_author(
                    name=user["username"] + " - Updating Bot",
                    icon_url=user["avatar_url"],
                    url=user["url"],
                )

                embed.set_footer(text=f"Updating Modmail v{self.version} -> v{latest.version}")

                embed.description = latest.description
                for name, value in latest.fields.items():
                    embed.add_field(name=name, value=value)

                channel = self.update_channel
                await channel.send(embed=embed)
            else:
                command = "git pull"
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stderr=PIPE,
                    stdout=PIPE,
                )
                err = await proc.stderr.read()
                err = err.decode("utf-8").rstrip()
                res = await proc.stdout.read()
                res = res.decode("utf-8").rstrip()

                if err and not res:
                    logger.warning(f"Autoupdate failed: {err}")
                    self.autoupdate.cancel()
                    return

                elif res != "Already up to date.":
                    if os.getenv("PIPENV_ACTIVE"):
                        # Update pipenv if possible
                        await asyncio.create_subprocess_shell(
                            "pipenv sync",
                            stderr=PIPE,
                            stdout=PIPE,
                        )
                        message = ""
                    else:
                        message = "\n\nDo manually update dependencies if your bot has crashed."

                    logger.info("Bot has been updated.")
                    channel = self.update_channel
                    if self.hosting_method in (HostingMethod.PM2, HostingMethod.SYSTEMD):
                        embed = discord.Embed(title="Bot has been updated", color=self.main_color)
                        embed.set_footer(
                            text=f"Updating Modmail v{self.version} " f"-> v{latest.version} {message}"
                        )
                        if self.config["update_notifications"]:
                            await channel.send(embed=embed)
                    else:
                        embed = discord.Embed(
                            title="Bot has been updated and is logging out.",
                            description=f"If you do not have an auto-restart setup, please manually start the bot. {message}",
                            color=self.main_color,
                        )
                        embed.set_footer(text=f"Updating Modmail v{self.version} -> v{latest.version}")
                        if self.config["update_notifications"]:
                            await channel.send(embed=embed)
                    return await self.close()

    @autoupdate.before_loop
    async def before_autoupdate(self):
        await self.wait_for_connected()
        logger.debug("Starting autoupdate loop")

        if self.config.get("disable_autoupdates"):
            logger.warning("Autoupdates disabled.")
            self.autoupdate.cancel()
            return

        if self.hosting_method == HostingMethod.DOCKER:
            logger.warning("Autoupdates disabled as using Docker.")
            self.autoupdate.cancel()
            return

        if not self.config.get("github_token") and self.hosting_method == HostingMethod.HEROKU:
            logger.warning("GitHub access token not found.")
            logger.warning("Autoupdates disabled.")
            self.autoupdate.cancel()
            return

    def format_channel_name(self, author, exclude_channel=None, force_null=False):
        """Sanitises a username for use with text channel names

        Placed in main bot class to be extendable to plugins"""
        guild = self.modmail_guild

        if force_null:
            name = new_name = "null"
        else:
            if self.config["use_random_channel_name"]:
                to_hash = self.token.split(".")[-1] + str(author.id)
                digest = hashlib.md5(to_hash.encode("utf8"), usedforsecurity=False)
                name = new_name = digest.hexdigest()[-8:]
            elif self.config["use_user_id_channel_name"]:
                name = new_name = str(author.id)
            elif self.config["use_timestamp_channel_name"]:
                name = new_name = author.created_at.isoformat(sep="-", timespec="minutes")
            else:
                if self.config["use_nickname_channel_name"]:
                    author_member = self.guild.get_member(author.id)
                    name = author_member.display_name.lower()
                else:
                    name = author.name.lower()

                if force_null:
                    name = "null"

                name = new_name = (
                    "".join(l for l in name if l not in string.punctuation and l.isprintable()) or "null"
                ) + f"-{author.discriminator}"

        counter = 1
        existed = set(c.name for c in guild.text_channels if c != exclude_channel)
        while new_name in existed:
            new_name = f"{name}_{counter}"  # multiple channels with same name
            counter += 1

        return new_name


def main():
    try:
        # noinspection PyUnresolvedReferences
        import uvloop  # type: ignore

        logger.debug("Setting up with uvloop.")
        uvloop.install()
    except ImportError:
        pass

    try:
        import cairosvg  # noqa: F401
    except OSError:
        if os.name == "nt":
            if struct.calcsize("P") * 8 != 64:
                logger.error(
                    "Unable to import cairosvg, ensure your Python is a 64-bit version: https://www.python.org/downloads/"
                )
            else:
                logger.error(
                    "Unable to import cairosvg, install GTK Installer for Windows and restart your system (https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases/latest)"
                )
        else:
            if "ubuntu" in platform.version().lower() or "debian" in platform.version().lower():
                logger.error(
                    "Unable to import cairosvg, try running `sudo apt-get install libpangocairo-1.0-0` or report on our support server with your OS details: https://discord.gg/etJNHCQ"
                )
            else:
                logger.error(
                    "Unable to import cairosvg, report on our support server with your OS details: https://discord.gg/etJNHCQ"
                )
        sys.exit(0)

    # check discord version
    discord_version = "2.0.1"
    if discord.__version__ != discord_version:
        logger.error(
            "Dependencies are not updated, run pipenv install. discord.py version expected %s, received %s",
            discord_version,
            discord.__version__,
        )
        sys.exit(0)

    # Set up discord.py internal logging
    if os.environ.get("LOG_DISCORD"):
        logger.debug(f"Discord logging enabled: {os.environ['LOG_DISCORD'].upper()}")
        d_logger = logging.getLogger("discord")

        d_logger.setLevel(os.environ["LOG_DISCORD"].upper())
        handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
        handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
        d_logger.addHandler(handler)

    bot = ModmailBot()
    bot.run()


if __name__ == "__main__":
    main()
