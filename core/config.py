import asyncio
import json
import os
import typing
from copy import deepcopy

import isodate

import discord
from discord.ext.commands import BadArgument

from core._color_data import ALL_COLORS
from core.models import InvalidConfigError
from core.time import UserFriendlyTime


class ConfigManager:

    public_keys = {
        # activity
        "twitch_url": 'https://www.twitch.tv/discord-modmail/',
        # bot settings
        "main_category_id": None,
        "prefix": '?',
        "mention": '@here',
        "main_color": discord.Color.blurple(),
        "user_typing": False,
        "mod_typing": False,
        "account_age": isodate.Duration(),
        "guild_age": isodate.Duration(),
        "reply_without_command": False,
        # logging
        "log_channel_id": None,
        # threads
        "sent_emoji": '✅',
        "blocked_emoji": '🚫',
        "close_emoji": '🔒',
        "recipient_thread_close": False,
        "thread_auto_close": 0,
        "thread_auto_close_response": "This thread has been closed automatically due to inactivity after {timeout}.",
        "thread_creation_response": "The staff team will get back to you as soon as possible.",
        "thread_creation_footer": None,
        "thread_creation_title": 'Thread Created',
        "thread_close_footer": 'Replying will create a new thread',
        "thread_close_title": 'Thread Closed',
        "thread_close_response": '{closer.mention} has closed this Modmail thread.',
        "thread_self_close_response": 'You have closed this Modmail thread.',
        # moderation
        "recipient_color": discord.Color.gold(),
        "mod_tag": None,
        "mod_color": discord.Color.green(),
        # anonymous message
        "anon_username": None,
        "anon_avatar_url": None,
        "anon_tag": 'Response',
    }

    private_keys = {
        # bot presence
        "activity_message": '',
        "activity_type": None,
        "status": None,
        "oauth_whitelist": [],
        # moderation
        "blocked": {},
        "blocked_whitelist": [],
        "command_permissions": {},
        "level_permissions": {},
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
        "log_url": 'https://example.com/',
        "log_url_prefix": '/logs',
        "mongo_uri": None,
        "owners": None,
        # bot
        "token": None,
        # Logging
        "log_level": "INFO",
    }

    colors = {"mod_color", "recipient_color", "main_color"}

    time_deltas = {"account_age", "guild_age", "thread_auto_close"}

    defaults = {**public_keys, **private_keys, **protected_keys}
    all_keys = set(defaults.keys())

    def __init__(self, bot):
        self.bot = bot
        self._cache = {}
        self.ready_event = asyncio.Event()
        self.populate_cache()

    def __repr__(self):
        return repr(self._cache)

    @property
    def api(self):
        return self.bot.api

    def populate_cache(self) -> dict:
        data = deepcopy(self.defaults)

        # populate from env var and .env file
        data.update({k.lower(): v for k, v in os.environ.items() if k.lower() in self.all_keys})

        if os.path.exists("config.json"):
            with open("config.json") as f:
                # Config json should override env vars
                data.update({k.lower(): v for k, v in json.load(f).items() if k.lower() in self.all_keys})

        self._cache = data
        return self._cache

    async def clean_data(self, key: str, val: typing.Any) -> typing.Tuple[str, str]:
        value_text = val
        clean_value = val

        # when setting a color
        if key in self.colors:
            hex_ = ALL_COLORS.get(val)

            if hex_ is None:
                hex_ = str(hex_)
                if hex_.startswith("#"):
                    hex_ = hex_[1:]
                if len(hex_) == 3:
                    hex_ = ''.join(s for s in hex_ for _ in range(2))
                if len(hex_) != 6:
                    raise InvalidConfigError("Invalid color name or hex.")
                try:
                    int(val, 16)
                except ValueError:
                    raise InvalidConfigError("Invalid color name or hex.")
                clean_value = "#" + val
                value_text = clean_value
            else:
                clean_value = hex_
                value_text = f"{val} ({clean_value})"

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

        return clean_value, value_text

    async def update(self):
        """Updates the config with data from the cache"""
        await self.api.update_config(self._cache)

    async def refresh(self) -> dict:
        """Refreshes internal cache with data from database"""
        data = await self.api.get_config()
        self._cache.update(data)
        self.ready_event.set()
        return self._cache

    async def wait_until_ready(self) -> None:
        await self.ready_event.wait()

    def __setitem__(self, key: str, item: typing.Any) -> None:
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        self._cache[key] = item

    def __getitem__(self, key: str) -> typing.Any:
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        if key not in self._cache:
            val = deepcopy(self.defaults[key])
            self._cache[key] = val
        return self._cache[key]

    def get(self, key: str, default: typing.Any = None) -> typing.Any:
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        if key not in self._cache:
            self._cache[key] = default
        return self._cache[key]

    def set(self, key: str, item: typing.Any) -> None:
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        self._cache[key] = item

    def remove(self, key: str) -> typing.Any:
        if key not in self.all_keys:
            raise InvalidConfigError(f'Configuration "{key}" is invalid.')
        self._cache[key] = deepcopy(self.defaults[key])
        return self._cache[key]

    def items(self) -> typing.Iterable:
        return self._cache.items()

    def filter_valid(self, data: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        return {k.lower(): v for k, v in data.items()
                if k.lower() in self.public_keys or k.lower() in self.private_keys}
