import asyncio
import json
import os

from core._color_data import ALL_COLORS
from core.models import Bot, ConfigManagerABC, InvalidConfigError


class ConfigManager:
    """Class that manages a cached configuration"""

    allowed_to_change_in_command = {
        'log_channel_id', 'mention', 'disable_autoupdates', 'prefix',
        'main_category_id', 'sent_emoji', 'blocked_emoji',
        'thread_creation_response', 'twitch_url', 'mod_color', 
        'recipient_color', 'mod_tag', 'anon_username', 'anon_avatar_url',
        'anon_tag'
    }

    internal_keys = {
        'snippets', 'aliases', 'blocked',
        'notification_squad', 'subscriptions',
        'closures', 'activity_message', 'activity_type',
        'plugins'
    }

    protected_keys = {
        'token', 'owners', 'modmail_api_token', 'guild_id', 'modmail_guild_id', 
        'mongo_uri', 'github_access_token', 'log_url'
    }

    # plugins is internal as its a list and i dont want weird issues

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
        }

        try:
            data.update(json.load(open('config.json')))
        except FileNotFoundError:
            pass
        finally:
            data.update(os.environ)
            self.cache = {
                k.lower(): v for k, v in data.items()
                if k.lower() in self.valid_keys
            }

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
