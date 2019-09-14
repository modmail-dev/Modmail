import asyncio
import json
import logging
import os
import re
import typing
from copy import deepcopy

from dotenv import load_dotenv
import isodate

import discord
from discord.ext.commands import BadArgument

from core._color_data import ALL_COLORS
from core.models import InvalidConfigError, Default
from core.time import UserFriendlyTime
from core.utils import strtobool

logger = logging.getLogger("Modmail")
load_dotenv()


class ConfigManager:

    public_keys = {
        # activity
        "twitch_url": "https://www.twitch.tv/discordmodmail/",
        # bot settings
        "main_category_id": None,
        "prefix": "?",
        "mention": "@here",
        "main_color": str(discord.Color.blurple()),
        "user_typing": False,
        "mod_typing": False,
        "account_age": None,
        "guild_age": None,
        "reply_without_command": False,
        # logging
        "log_channel_id": None,
        # threads
        "sent_emoji": "✅",
        "blocked_emoji": "🚫",
        "close_emoji": "🔒",
        "recipient_thread_close": False,
        "thread_auto_close_silently": False,
        "thread_auto_close": None,
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
        "owners": None,
        # bot
        "token": None,
        # Logging
        "log_level": "INFO",
    }

    colors = {"mod_color", "recipient_color", "main_color"}

    time_deltas = {"account_age", "guild_age", "thread_auto_close"}

    booleans = {
        "user_typing",
        "mod_typing",
        "reply_without_command",
        "recipient_thread_close",
        "thread_auto_close_silently",
        "thread_move_notify",
    }

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
        data.update(
            {k.lower(): v for k, v in os.environ.items() if k.lower() in self.all_keys}
        )
        config_json = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
        )
        if os.path.exists(config_json):
            logger.debug("Loading envs from config.json.")
            with open(config_json, "r") as f:
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
                    logger.critical(
                        "Failed to load config.json env values.", exc_info=True
                    )
        self._cache = data

        config_help_json = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config_help.json"
        )
        with open(config_help_json, "r", encoding="utf-8") as f:
            self.config_help = dict(sorted(json.load(f).items()))

        return self._cache

    async def clean_data(self, key: str, val: typing.Any) -> typing.Tuple[str, str]:
        value_text = val
        clean_value = val

        # when setting a color
        if key in self.colors:
            try:
                hex_ = str(val)

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
                hex_ = "#" + hex_
                value_text = clean_value = hex_

            except InvalidConfigError:
                name = str(val).lower()
                name = re.sub(r"[\-+|. ]+", " ", name)
                hex_ = ALL_COLORS.get(name)
                if hex_ is None:
                    name = re.sub(r"[\-+|. ]+", "", name)
                    hex_ = ALL_COLORS.get(name)
                    if hex_ is None:
                        raise

                clean_value = hex_
                value_text = f"{name} ({clean_value})"

        elif key in self.time_deltas:
            try:
                isodate.parse_duration(val)
            except isodate.ISO8601Error:
                try:
                    converter = UserFriendlyTime()
                    time = await converter.convert(None, val)
                    if time.arg:
                        raise ValueError
                except BadArgument as exc:
                    raise InvalidConfigError(*exc.args)
                except Exception:
                    raise InvalidConfigError(
                        "Unrecognized time, please use ISO-8601 duration format "
                        'string or a simpler "human readable" time.'
                    )
                clean_value = isodate.duration_isoformat(time.dt - converter.now)
                value_text = f"{val} ({clean_value})"

        elif key in self.booleans:
            try:
                clean_value = value_text = strtobool(val)
            except ValueError:
                raise InvalidConfigError("Must be a yes/no value.")

        return clean_value, value_text

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
            logger.info("Successfully fetched configurations from database.")
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

    def get(self, key: str, default: typing.Any = Default) -> typing.Any:
        key = key.lower()
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        if key not in self._cache:
            if default is Default:
                self._cache[key] = deepcopy(self.defaults[key])
        if default is not Default and self._cache[key] == self.defaults[key]:
            self._cache[key] = default
        return self._cache[key]

    def set(self, key: str, item: typing.Any) -> None:
        key = key.lower()
        logger.info("Setting %s.", key)
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        self._cache[key] = item

    def remove(self, key: str) -> typing.Any:
        key = key.lower()
        logger.info("Removing %s.", key)
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        self._cache[key] = deepcopy(self.defaults[key])
        return self._cache[key]

    def items(self) -> typing.Iterable:
        return self._cache.items()

    @classmethod
    def filter_valid(
        cls, data: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
        return {
            k.lower(): v
            for k, v in data.items()
            if k.lower() in cls.public_keys or k.lower() in cls.private_keys
        }

    @classmethod
    def filter_default(
        cls, data: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
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
