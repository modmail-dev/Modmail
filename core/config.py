import asyncio
import json
import os

import isodate

from discord.ext.commands import BadArgument

from core._color_data import ALL_COLORS
from core.models import Bot, ConfigManagerABC, InvalidConfigError
from core.time import UserFriendlyTime


class ConfigManager(ConfigManagerABC):

    allowed_to_change_in_command = {
        # activity
        'twitch_url',

        # bot settings
        'main_category_id', 'disable_autoupdates', 'prefix', 'mention',
        'main_color', 'user_typing', 'mod_typing', 'account_age', 

        # logging
        'log_channel_id',

        # threads
        'sent_emoji', 'blocked_emoji', 'close_emoji', 'disable_recipient_thread_close',
        'thread_creation_response', 'thread_creation_footer', 'thread_creation_title',
        'thread_close_footer', 'thread_close_title', 'thread_close_response',
        'thread_self_close_response',
        
        # moderation
        'recipient_color', 'mod_tag', 'mod_color',

        # anonymous message
        'anon_username', 'anon_avatar_url', 'anon_tag'
    }

    internal_keys = {
        # bot presence
        'activity_message', 'activity_type', 'status',

        # moderation
        'blocked',

        # threads
        'snippets', 'notification_squad', 'subscriptions', 'closures',

        # misc
        'aliases', 'plugins'
    }

    protected_keys = {
        # Modmail
        'modmail_api_token', 'modmail_guild_id', 'guild_id', 'owners',
        'log_url', 'mongo_uri',

        # bot
        'token',

        # GitHub
        'github_access_token',

        # Logging
        'log_level'
    }

    colors = {
        'mod_color', 'recipient_color', 'main_color'
    }

    time_deltas = {
        'account_age'
    }

    valid_keys = allowed_to_change_in_command | internal_keys | protected_keys

    def __init__(self, bot: Bot):
        self.bot = bot
        self._cache = {}
        self._ready_event = asyncio.Event()
        self.populate_cache()

    def __repr__(self):
        return repr(self.cache)

    @property
    def api(self):
        return self.bot.api

    @property
    def ready_event(self):
        return self._ready_event

    @property
    def cache(self):
        return self._cache

    @cache.setter
    def cache(self, val):
        self._cache = val

    def populate_cache(self):
        data = {
            'snippets': {},
            'plugins': [],
            'aliases': {},
            'blocked': {},
            'notification_squad': {},
            'subscriptions': {},
            'closures': {},
            'log_level': 'INFO'
        }

        data.update(os.environ)

        if os.path.exists('config.json'):
            with open('config.json') as f:
                # Config json should override env vars
                data.update(json.load(f))

        self.cache = {
            k.lower(): v for k, v in data.items()
            if k.lower() in self.valid_keys
        }
        return self.cache

    async def clean_data(self, key, val):
        value_text = val
        clean_value = val

        # when setting a color
        if key in self.colors:
            hex_ = ALL_COLORS.get(val)

            if hex_ is None:
                if not isinstance(val, str):
                    raise InvalidConfigError('Invalid color name or hex.')
                if val.startswith('#'):
                    val = val[1:]
                if len(val) != 6:
                    raise InvalidConfigError('Invalid color name or hex.')
                for v in val:
                    if v not in {'0', '1', '2', '3', '4', '5', '6', '7',
                                 '8', '9', 'a', 'b', 'c', 'd', 'e', 'f'}:
                        raise InvalidConfigError('Invalid color name or hex.')
                clean_value = '#' + val
                value_text = clean_value
            else:
                clean_value = hex_
                value_text = f'{val} ({clean_value})'

        elif key in self.time_deltas:
            try:
                isodate.parse_duration(val)
            except isodate.ISO8601Error:
                try:
                    converter = UserFriendlyTime()
                    time = await converter.convert(None, val)
                    if time.arg:
                        raise ValueError
                except BadArgument as e:
                    raise InvalidConfigError(*e.args)
                except Exception:
                    raise InvalidConfigError(
                        'Unrecognized time, please use ISO-8601 duration format '
                        'string or a simpler "human readable" time.'
                    )
                clean_value = isodate.duration_isoformat(time.dt - converter.now)
                value_text = f'{val} ({clean_value})'

        return clean_value, value_text

    async def update(self, data=None):
        """Updates the config with data from the cache"""
        if data is not None:
            self.cache.update(data)
        await self.api.update_config(self.cache)
        return self.cache

    async def refresh(self):
        """Refreshes internal cache with data from database"""
        data = await self.api.get_config()
        self.cache.update(data)
        self.ready_event.set()
        return self.cache

    async def wait_until_ready(self):
        await self.ready_event.wait()

    def __getattr__(self, value):
        return self.cache[value]

    def __setitem__(self, key, item):
        self.cache[key] = item

    def __getitem__(self, key):
        return self.cache[key]

    def get(self, key, default=None):
        return self.cache.get(key, default)
