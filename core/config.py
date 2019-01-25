import asyncio
import os
import json
from typing import Optional, Any

import box


class ConfigManager:
    """Class that manages a cached configuration"""

    allowed_to_change_in_command = {
        # activity
        'activity_message', 'activity_type', 'twitch_url',
        # bot settings
        'main_category_id', 'disable_autoupdates', 'prefix', 'mention',
        # logging
        'log_channel_id',
        # threads
        'sent_emoji', 'blocked_emoji', 'thread_creation_response',
        # moderation
        'recipient_color', 'mod_tag', 'mod_color',
        # anonymous message
        'anon_username', 'anon_avatar_url', 'anon_tag'
        }
    
    internal_keys = {
        'snippets', 'aliases', 'blocked',
        'notification_squad', 'subscriptions',
        'closures'
        }
    
    protected_keys = {
        'token', 'owners', 'modmail_api_token',
        'guild_id', 'modmail_guild_id',
        'mongo_uri', 'github_access_token', 'log_url'
        }

    valid_keys = allowed_to_change_in_command | internal_keys | protected_keys

    def __init__(self, bot):
        self.bot = bot
        self.cache = box.Box()
        self.ready_event = asyncio.Event()
        self.populate_cache()
    
    def __repr__(self):
        return repr(self.cache)

    @property
    def api(self):
        return self.bot.modmail_api

    def populate_cache(self) -> dict:
        data = {
            'snippets': {},
            'aliases': {},
            'blocked': {},
            'notification_squad': {},
            'subscriptions': {},
            'closures': {},
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

    async def update(self, data: Optional[dict] = None) -> dict:
        """Updates the config with data from the cache"""
        if data is not None:
            self.cache.update(data)
        await self.api.update_config(self.cache)
        return self.cache

    async def refresh(self) -> dict:
        """Refreshes internal cache with data from database"""
        data = await self.api.get_config()
        self.cache.update(data)
        self.ready_event.set()
        return self.cache
    
    async def wait_until_ready(self) -> None:
        await self.ready_event.wait()

    def __getattr__(self, value: str):
        return self.cache[value]

    def __setitem__(self, key: str, item: Any):
        self.cache[key] = item

    def __getitem__(self, key: str):
        return self.cache[key]

    def get(self, key: str, default: Any = None):
        return self.cache.get(key, default)
