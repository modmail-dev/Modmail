import secrets
from datetime import datetime
from json import JSONDecodeError
from typing import Union, Optional

from aiohttp import ClientResponseError, ClientResponse
from discord import Member, DMChannel

from core.models import Bot, UserClient


class ApiClient:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.session = bot.session
        self.headers: dict = None

    async def request(self, url: str,
                      method: str = 'GET',
                      payload: dict = None,
                      return_response: bool = False,
                      headers: dict = None) -> Union[ClientResponse,
                                                     dict, str]:
        if headers is not None:
            headers.update(self.headers)
        else:
            headers = self.headers
        async with self.session.request(method, url, headers=headers,
                                        json=payload) as resp:
            if return_response:
                return resp
            try:
                return await resp.json()
            except (JSONDecodeError, ClientResponseError):
                return await resp.text()

    def filter_valid(self, data):
        valid_keys = self.bot.config.valid_keys.difference(
            self.bot.config.protected_keys
        )
        return {k: v for k, v in data.items() if k in valid_keys}


class Github(ApiClient):
    BASE = 'https://api.github.com'
    REPO = BASE + '/repos/kyb3r/modmail'
    head = REPO + '/git/refs/heads/master'
    MERGE_URL = BASE + '/repos/{username}/modmail/merges'
    FORK_URL = REPO + '/forks'
    STAR_URL = BASE + '/user/starred/kyb3r/modmail'

    def __init__(self, bot: Bot,
                 access_token: str = None,
                 username: str = None,
                 **kwargs):
        super().__init__(bot)
        self.access_token = access_token
        self.username = username
        self.id: str = kwargs.pop('id')
        self.avatar_url: str = kwargs.pop('avatar_url')
        self.url: str = kwargs.pop('url')
        if self.access_token:
            self.headers = {'Authorization': 'token ' + str(access_token)}

    async def update_repository(self, sha: str = None) -> Optional[dict]:
        if sha is None:
            resp: dict = await self.request(self.head)
            sha = resp['object']['sha']

        payload = {
            'base': 'master',
            'head': sha,
            'commit_message': 'Updating bot'
        }

        merge_url = self.MERGE_URL.format(username=self.username)

        resp = await self.request(merge_url, method='POST', payload=payload)
        if isinstance(resp, dict):
            return resp

    async def fork_repository(self) -> None:
        await self.request(self.FORK_URL, method='POST')

    async def has_starred(self) -> bool:
        resp = await self.request(self.STAR_URL, return_response=True)
        return resp.status == 204

    async def star_repository(self) -> None:
        await self.request(self.STAR_URL, method='PUT',
                           headers={'Content-Length': '0'})

    @classmethod
    async def login(cls, bot) -> 'Github':
        self = cls(bot, bot.config.get('github_access_token'), )
        resp: dict = await self.request('https://api.github.com/user')
        self.username: str = resp['login']
        self.avatar_url: str = resp['avatar_url']
        self.url: str = resp['html_url']
        self.id: str = str(resp['id'])
        print(f'Logged in to: {self.username} - {self.id}')
        return self


class ModmailApiClient(UserClient, ApiClient):
    BASE = 'https://api.modmail.tk'
    METADATA = BASE + '/metadata'
    GITHUB = BASE + '/github'
    LOGS = BASE + '/logs'
    CONFIG = BASE + '/config'

    def __init__(self, bot: Bot):
        super().__init__(bot)
        if self.token:
            self.headers = {
                'Authorization': 'Bearer ' + self.token
            }

    @property
    def token(self):
        return self.bot.config.get('modmail_api_token')

    async def validate_token(self):
        resp = await self.request(self.BASE + '/token/verify',
                                  return_response=True)
        return resp.status == 200

    async def post_metadata(self, data):
        return await self.request(self.METADATA, method='POST', payload=data)

    async def get_user_info(self):
        return await self.request(self.GITHUB + '/userinfo')

    async def update_repository(self):
        return await self.request(self.GITHUB + '/update')

    async def get_metadata(self):
        return await self.request(self.METADATA)

    async def get_user_logs(self, user_id):
        return await self.request(self.LOGS + '/user/' + str(user_id))

    async def get_log(self, channel_id):
        return await self.request(self.LOGS + '/' + str(channel_id))

    async def get_log_link(self, channel_id):
        doc = await self.get_log(channel_id)
        return f'https://logs.modmail.tk/{doc["key"]}'

    async def get_config(self):
        return await self.request(self.CONFIG)

    async def update_config(self, data):
        data = self.filter_valid(data)
        return await self.request(self.CONFIG, method='PATCH', payload=data)

    async def create_log_entry(self, recipient, channel, creator):
        return await self.request(self.LOGS + '/key', payload={
            'channel_id': str(channel.id),
            'guild_id': str(self.bot.guild_id),
            'recipient': {
                'id': str(recipient.id),
                'name': recipient.name,
                'discriminator': recipient.discriminator,
                'avatar_url': recipient.avatar_url,
                'mod': False
            },
            'creator': {
                'id': str(creator.id),
                'name': creator.name,
                'discriminator': creator.discriminator,
                'avatar_url': creator.avatar_url,
                'mod': isinstance(creator, Member)
            }
        })

    async def edit_message(self, message_id, new_content):
        await self.request(self.LOGS + '/edit', method='PATCH',
                           payload={
                               'message_id': str(message_id),
                               'new_content': new_content
                           })

    async def append_log(self, message, channel_id='', type_='thread_message'):
        channel_id = str(channel_id) or str(message.channel.id)
        data = {
            'payload': {
                'timestamp': str(message.created_at),
                'message_id': str(message.id),
                # author
                'author': {
                    'id': str(message.author.id),
                    'name': message.author.name,
                    'discriminator': message.author.discriminator,
                    'avatar_url': message.author.avatar_url,
                    'mod': not isinstance(message.channel, DMChannel),
                },
                # message properties
                'content': message.content,
                'type': type_,
                'attachments': [
                    {
                        'id': a.id,
                        'filename': a.filename,
                        'is_image': a.width is not None,
                        'size': a.size,
                        'url': a.url
                    } for a in message.attachments]
            }
        }
        return await self.request(self.LOGS + f'/{channel_id}',
                                  method='PATCH',
                                  payload=data)

    async def post_log(self, channel_id, data):
        return await self.request(self.LOGS + f'/{channel_id}',
                                  method='POST',
                                  payload=data)


class SelfHostedClient(UserClient, ApiClient):
    BASE = 'https://api.modmail.tk'
    METADATA = BASE + '/metadata'

    def __init__(self, bot: Bot):
        super().__init__(bot)
        if self.token:
            self.headers = {
                'Authorization': 'Bearer ' + self.token
            }

    @property
    def token(self):
        return self.bot.config.get('github_access_token')

    @property
    def db(self):
        return self.bot.db

    @property
    def logs(self):
        return self.db.logs

    async def validate_token(self):
        resp = await self.request(self.BASE + '/token/verify',
                                  return_response=True)
        return resp.status == 200

    async def get_metadata(self):
        return await self.request(self.METADATA)

    async def post_metadata(self, data):
        return await self.request(self.METADATA, method='POST', payload=data)

    async def get_user_logs(self, user_id):
        query = {
            'recipient.id': str(user_id), 
            'guild_id': str(self.bot.guild_id)
            }
        
        projection = {
            'messages': {'$slice': 5}
        }
        return await self.logs.find(query, projection).to_list(None)

    async def get_log(self, channel_id):
        return await self.logs.find_one({'channel_id': str(channel_id)})

    async def get_log_link(self, channel_id):
        doc = await self.get_log(channel_id)
        return f"{self.bot.config.log_url.strip('/')}/logs/{doc['key']}"

    async def create_log_entry(self, recipient, channel, creator):
        key = secrets.token_hex(6)

        await self.logs.insert_one({
            'key': key,
            'open': True,
            'created_at': str(datetime.utcnow()),
            'closed_at': None,
            'channel_id': str(channel.id),
            'guild_id': str(self.bot.guild_id),
            'recipient': {
                'id': str(recipient.id),
                'name': recipient.name,
                'discriminator': recipient.discriminator,
                'avatar_url': recipient.avatar_url,
                'mod': False
            },
            'creator': {
                'id': str(creator.id),
                'name': creator.name,
                'discriminator': creator.discriminator,
                'avatar_url': creator.avatar_url,
                'mod': isinstance(creator, Member)
            },
            'closer': None,
            'messages': []
        })

        return f"{self.bot.config.log_url.strip('/')}/logs/{key}"

    async def get_config(self):
        conf = await self.db.config.find_one({'bot_id': self.bot.user.id})
        if conf is None:
            await self.db.config.insert_one({'bot_id': self.bot.user.id})
            return {'bot_id': self.bot.user.id}
        return conf

    async def update_config(self, data):
        data = self.filter_valid(data)
        return await self.db.config.update_one({'bot_id': self.bot.user.id},
                                               {'$set': data})

    async def edit_message(self, message_id, new_content):
        await self.logs.update_one({
            'messages.message_id': str(message_id)
        }, {
            '$set': {
                'messages.$.content': new_content,
                'messages.$.edited': True
            }
        })

    async def append_log(self, message, channel_id='', type_='thread_message'):
        channel_id = str(channel_id) or str(message.channel.id)
        data = {
            'timestamp': str(message.created_at),
            'message_id': str(message.id),
            'author': {
                'id': str(message.author.id),
                'name': message.author.name,
                'discriminator': message.author.discriminator,
                'avatar_url': message.author.avatar_url,
                'mod': not isinstance(message.channel, DMChannel),
            },
            'content': message.content,
            'type': type_,
            'attachments': [
                {
                    'id': a.id,
                    'filename': a.filename,
                    'is_image': a.width is not None,
                    'size': a.size,
                    'url': a.url
                } for a in message.attachments
            ]
        }

        return await self.logs.find_one_and_update(
            {'channel_id': channel_id},
            {'$push': {f'messages': data}},
            return_document=True
        )

    async def post_log(self, channel_id, data):
        return await self.logs.find_one_and_update(
            {'channel_id': str(channel_id)},
            {'$set': {k: v for k, v in data.items()}},
            return_document=True
        )

    async def update_repository(self):
        user = await Github.login(self.bot)
        data = await user.update_repository()
        return {
            'data': data,
            'user': {
                'username': user.username,
                'avatar_url': user.avatar_url,
                'url': user.url
            }
        }

    async def get_user_info(self):
        user = await Github.login(self.bot)
        return {
            'user': {
                'username': user.username,
                'avatar_url': user.avatar_url,
                'url': user.url
            }
        }
