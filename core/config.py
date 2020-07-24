import asyncio
import json
import os
import re
import typing
from copy import deepcopy

from dotenv import load_dotenv
import isodate

import discord
from discord.ext.commands import BadArgument

from core._color_data import ALL_COLORS
from core.models import InvalidConfigError, Default, getLogger
from core.time import UserFriendlyTimeSync
from core.utils import strtobool

logger = getLogger(__name__)
load_dotenv()


class ConfigManager:

    public_keys = {
        # activity
        "twitch_url": "https://www.twitch.tv/discordmodmail/",
        # bot settings
        "main_category_id": None,
        "fallback_category_id": None,
        "prefix": "?",
        "mention": "@here",
        "main_color": str(discord.Color.blurple()),
        "error_color": str(discord.Color.red()),
        "user_typing": False,
        "mod_typing": False,
        "account_age": isodate.Duration(),
        "guild_age": isodate.Duration(),
        "thread_cooldown": isodate.Duration(),
        "reply_without_command": False,
        "anon_reply_without_command": False,
        # logging
        "log_channel_id": None,
        # threads
        "sent_emoji": "✅",
        "blocked_emoji": "🚫",
        "close_emoji": "🔒",
        "recipient_thread_close": False,
        "thread_auto_close_silently": False,
        "thread_auto_close": isodate.Duration(),
        "thread_auto_close_response": "This thread has been closed automatically due to inactivity after {timeout}.",
        "thread_creation_response": "The staff team will get back to you as soon as possible.",
        "thread_creation_footer": "Your message has been sent",
        "thread_self_closable_creation_footer": "Click the lock to close the thread",
        "thread_creation_title": "Thread Created",
        "thread_close_footer": "Replying will create a new thread",
        "thread_close_title": "Thread Closed",
        "thread_close_response": "{closer.mention} has closed this Modmail thread.",
        "thread_self_close_response": "You have closed this Modmail thread.",
        "thread_move_notify": False,
        "thread_move_response": "This thread has been moved.",
        "disabled_new_thread_title": "Not Delivered",
        "disabled_new_thread_response": "We are not accepting new threads.",
        "disabled_new_thread_footer": "Please try again later...",
        "disabled_current_thread_title": "Not Delivered",
        "disabled_current_thread_response": "We are not accepting any messages.",
        "disabled_current_thread_footer": "Please try again later...",
        # moderation
        "recipient_color": str(discord.Color.gold()),
        "mod_color": str(discord.Color.green()),
        "mod_tag": None,
        # anonymous message
        "anon_username": None,
        "anon_avatar_url": None,
        "anon_tag": "Response",
    }

    private_keys = {
        # bot presence
        "activity_message": "",
        "activity_type": None,
        "status": None,
        # dm_disabled 0 = none, 1 = new threads, 2 = all threads
        # TODO: use enum
        "dm_disabled": 0,
        "oauth_whitelist": [],
        # moderation
        "blocked": {},
        "blocked_whitelist": [],
        "command_permissions": {},
        "level_permissions": {},
        "override_command_level": {},
        # threads
        "snippets": {},
        "notification_squad": {},
        "subscriptions": {},
        "closures": {},
        # misc
        "plugins": [],
        "aliases": {},
    }

    protected_keys = {
        # Modmail
        "modmail_guild_id": None,
        "guild_id": None,
        "log_url": "https://example.com/",
        "log_url_prefix": "/logs",
        "mongo_uri": None,
        "database_type": "mongodb",
        "connection_uri": None,  # replace mongo uri in the future
        "owners": None,
        # bot
        "token": None,
        "enable_plugins": True,
        "enable_eval": True,
        # github access token for private repositories
        "github_token": None,
        # Logging
        "log_level": "INFO",
    }

    colors = {"mod_color", "recipient_color", "main_color", "error_color"}

    time_deltas = {"account_age", "guild_age", "thread_auto_close", "thread_cooldown"}

    booleans = {
        "user_typing",
        "mod_typing",
        "reply_without_command",
        "anon_reply_without_command",
        "recipient_thread_close",
        "thread_auto_close_silently",
        "thread_move_notify",
        "enable_plugins",
        "enable_eval",
    }

    special_types = {"status", "activity_type"}

    defaults = {**public_keys, **private_keys, **protected_keys}
    all_keys = set(defaults.keys())

    def __init__(self, bot):
        self.bot = bot
        self._cache = {}
        self.ready_event = asyncio.Event()
        self.config_help = {}

    def __repr__(self):
        return repr(self._cache)

    def populate_cache(self) -> dict:
        data = deepcopy(self.defaults)

        # populate from env var and .env file
        data.update({k.lower(): v for k, v in os.environ.items() if k.lower() in self.all_keys})
        config_json = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
        )
        if os.path.exists(config_json):
            logger.debug("Loading envs from config.json.")
            with open(config_json, "r", encoding="utf-8") as f:
                # Config json should override env vars
                try:
                    data.update(
                        {
                            k.lower(): v
                            for k, v in json.load(f).items()
                            if k.lower() in self.all_keys
                        }
                    )
                except json.JSONDecodeError:
                    logger.critical("Failed to load config.json env values.", exc_info=True)
        self._cache = data

        config_help_json = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config_help.json"
        )
        with open(config_help_json, "r", encoding="utf-8") as f:
            self.config_help = dict(sorted(json.load(f).items()))

        return self._cache

    async def update(self):
        """Updates the config with data from the cache"""
        await self.bot.api.update_config(self.filter_default(self._cache))

    async def refresh(self) -> dict:
        """Refreshes internal cache with data from database"""
        for k, v in (await self.bot.api.get_config()).items():
            k = k.lower()
            if k in self.all_keys:
                self._cache[k] = v
        if not self.ready_event.is_set():
            self.ready_event.set()
            logger.debug("Successfully fetched configurations from database.")
        return self._cache

    async def wait_until_ready(self) -> None:
        await self.ready_event.wait()

    def __setitem__(self, key: str, item: typing.Any) -> None:
        key = key.lower()
        logger.info("Setting %s.", key)
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        self._cache[key] = item

    def __getitem__(self, key: str) -> typing.Any:
        key = key.lower()
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        if key not in self._cache:
            self._cache[key] = deepcopy(self.defaults[key])
        return self._cache[key]

    def __delitem__(self, key: str) -> None:
        return self.remove(key)

    def get(self, key: str, convert=True) -> typing.Any:
        value = self.__getitem__(key)

        if not convert:
            return value

        if key in self.colors:
            try:
                return int(value.lstrip("#"), base=16)
            except ValueError:
                logger.error("Invalid %s provided.", key)
            value = int(self.remove(key).lstrip("#"), base=16)

        elif key in self.time_deltas:
            if not isinstance(value, isodate.Duration):
                try:
                    value = isodate.parse_duration(value)
                except isodate.ISO8601Error:
                    logger.warning(
                        "The {account} age limit needs to be a "
                        'ISO-8601 duration formatted duration, not "%s".',
                        value,
                    )
                    value = self.remove(key)

        elif key in self.booleans:
            try:
                value = strtobool(value)
            except ValueError:
                value = self.remove(key)

        elif key in self.special_types:
            if value is None:
                return None

            if key == "status":
                try:
                    # noinspection PyArgumentList
                    value = discord.Status(value)
                except ValueError:
                    logger.warning("Invalid status %s.", value)
                    value = self.remove(key)

            elif key == "activity_type":
                try:
                    # noinspection PyArgumentList
                    value = discord.ActivityType(value)
                except ValueError:
                    logger.warning("Invalid activity %s.", value)
                    value = self.remove(key)

        return value

    def set(self, key: str, item: typing.Any, convert=True) -> None:
        if not convert:
            return self.__setitem__(key, item)

        if key in self.colors:
            try:
                hex_ = str(item)
                if hex_.startswith("#"):
                    hex_ = hex_[1:]
                if len(hex_) == 3:
                    hex_ = "".join(s for s in hex_ for _ in range(2))
                if len(hex_) != 6:
                    raise InvalidConfigError("Invalid color name or hex.")
                try:
                    int(hex_, 16)
                except ValueError:
                    raise InvalidConfigError("Invalid color name or hex.")

            except InvalidConfigError:
                name = str(item).lower()
                name = re.sub(r"[\-+|. ]+", " ", name)
                hex_ = ALL_COLORS.get(name)
                if hex_ is None:
                    name = re.sub(r"[\-+|. ]+", "", name)
                    hex_ = ALL_COLORS.get(name)
                    if hex_ is None:
                        raise
            return self.__setitem__(key, "#" + hex_)

        if key in self.time_deltas:
            try:
                isodate.parse_duration(item)
            except isodate.ISO8601Error:
                try:
                    converter = UserFriendlyTimeSync()
                    time = converter.convert(None, item)
                    if time.arg:
                        raise ValueError
                except BadArgument as exc:
                    raise InvalidConfigError(*exc.args)
                except Exception as e:
                    logger.debug(e)
                    raise InvalidConfigError(
                        "Unrecognized time, please use ISO-8601 duration format "
                        'string or a simpler "human readable" time.'
                    )
                item = isodate.duration_isoformat(time.dt - converter.now)
            return self.__setitem__(key, item)

        if key in self.booleans:
            try:
                return self.__setitem__(key, strtobool(item))
            except ValueError:
                raise InvalidConfigError("Must be a yes/no value.")

        # elif key in self.special_types:
        #     if key == "status":

        return self.__setitem__(key, item)

    def remove(self, key: str) -> typing.Any:
        key = key.lower()
        logger.info("Removing %s.", key)
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        if key in self._cache:
            del self._cache[key]
        self._cache[key] = deepcopy(self.defaults[key])
        return self._cache[key]

    def items(self) -> typing.Iterable:
        return self._cache.items()

    @classmethod
    def filter_valid(cls, data: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        return {
            k.lower(): v
            for k, v in data.items()
            if k.lower() in cls.public_keys or k.lower() in cls.private_keys
        }

    @classmethod
    def filter_default(cls, data: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        # TODO: use .get to prevent errors
        filtered = {}
        for k, v in data.items():
            default = cls.defaults.get(k.lower(), Default)
            if default is Default:
                logger.error("Unexpected configuration detected: %s.", k)
                continue
            if v != default:
                filtered[k.lower()] = v
        return filtered
