from discord import Member, DMChannel, TextChannel, Message

import secrets
from datetime import datetime

from aiohttp import ClientResponseError, ClientResponse
from typing import Union, Optional
from json import JSONDecodeError
from pymongo import ReturnDocument

from bot import ModmailBot


class ApiClient:
    def __init__(self, bot: ModmailBot):
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


class Github(ApiClient):
    BASE = 'https://api.github.com'
    REPO = BASE + '/repos/kyb3r/modmail'
    head = REPO + '/git/refs/heads/master'
    MERGE_URL = BASE + '/repos/{username}/modmail/merges'
    FORK_URL = REPO + '/forks'
    STAR_URL = BASE + '/user/starred/kyb3r/modmail'

    def __init__(self, bot: ModmailBot,
                 access_token: str = None,
                 username: str = None):
        super().__init__(bot)
        self.access_token = access_token
        self.username = username
        # TODO: Find out type for id:
        self.id = None
        self.avatar_url: str = None
        self.url: str = None
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
                           headers={'Content-Length':  '0'})

    # TODO: Broken.
    async def get_latest_commits(self, limit=3):
        # resp = await self.request(self.commit_url)
        # for index in range(limit):
        #     yield resp[index]
        ...

    @classmethod
    async def login(cls, bot: ModmailBot) -> 'Github':
        self = cls(bot, bot.config.get('github_access_token'))
        resp: dict = await self.request('https://api.github.com/user')
        self.username: str = resp['login']
        self.avatar_url: str = resp['avatar_url']
        self.url: str = resp['html_url']
        self.id = resp['id']
        self.raw_data = resp
        print(f'Logged in to: {self.username} - {self.id}')
        return self


class ModmailApiClient(ApiClient):
    BASE = 'https://api.modmail.tk'
    METADATA = BASE + '/metadata'
    GITHUB = BASE + '/github'
    LOGS = BASE + '/logs'
    CONFIG = BASE + '/config'

    def __init__(self, bot: ModmailBot):
        super().__init__(bot)
        self.token: Optional[str] = bot.config.get('modmail_api_token')
        if self.token:
            self.headers = {
                'Authorization': 'Bearer ' + self.token
            }

    async def validate_token(self) -> bool:
        resp = await self.request(self.BASE + '/token/verify',
                                  return_response=True)
        return resp.status == 200

    def post_metadata(self, data: dict):
        return self.request(self.METADATA, method='POST', payload=data)

    def get_user_info(self):
        return self.request(self.GITHUB + '/userinfo')

    def update_repository(self):
        return self.request(self.GITHUB + '/update')

    def get_metadata(self):
        return self.request(self.BASE + '/metadata')

    def get_user_logs(self, user_id: Union[str, int]):
        return self.request(self.LOGS + '/user/' + str(user_id))

    def get_log(self, channel_id: Union[str, int]):
        return self.request(self.LOGS + '/' + str(channel_id))

    def get_config(self):
        return self.request(self.CONFIG)

    def update_config(self, data: dict):
        data = self.filter_valid(data)
        return self.request(self.CONFIG, method='PATCH', payload=data)

    def filter_valid(self, data: dict) -> dict:
        valid_keys = self.bot.config.valid_keys.difference(
            self.bot.config.protected_keys
        )
        return {k: v for k, v in data.items() if k in valid_keys}

    def get_log_url(self, recipient: Member,
                    channel: TextChannel,
                    creator: Member):
        return self.request(self.LOGS + '/key', payload={
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

    def append_log(self, message: Message, channel_id: Union[str, int] = '',
                   type_: str = 'thread_message'):

        channel_id = str(channel_id) or str(message.channel.id)
        payload = {
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
                'attachments': [i.url for i in message.attachments],
                'type': type_
            }
        }
        return self.request(self.LOGS + f'/{channel_id}',
                            method='PATCH',
                            payload=payload)

    def post_log(self, channel_id: Union[int, str], payload: dict):
        return self.request(self.LOGS + f'/{channel_id}',
                            method='POST',
                            payload=payload)


class SelfHostedClient(ModmailApiClient):

    def __init__(self, bot: ModmailBot):
        super().__init__(bot)
        self.token: Optional[str] = bot.config.get('github_access_token')
        if self.token:
            self.headers = {
                'Authorization': 'Bearer ' + self.token
            }

    @property
    def db(self):
        return self.bot.db
    
    @property 
    def logs(self):
        return self.db.logs

    async def get_user_logs(self, user_id: Union[int, str]):
        logs = []
        async for entry in self.logs.find({'recipient.id': str(user_id)}):
            logs.append(entry)
        return logs

    async def get_log(self, channel_id: Union[int, str]):
        return await self.logs.find_one({'channel_id': str(channel_id)})

    async def get_log_url(self, recipient: Member, channel: TextChannel,
                          creator: Member) -> str:
        key = secrets.token_hex(6)

        await self.logs.insert_one({
            'key': key,
            'open': True,
            'created_at': str(datetime.utcnow()),
            'closed_at': None,
            'channel_id': str(channel.id),
            'guild_id': str(channel.guild.id),
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

    async def get_config(self) -> dict:
        conf = await self.db.config.find_one({'bot_id': self.bot.user.id})
        if conf is None:
            await self.db.config.insert_one({'bot_id': self.bot.user.id})
            return {'bot_id': self.bot.user.id}
        return conf

    async def update_config(self, data: dict) -> dict:
        data = self.filter_valid(data)
        return await self.db.config.update_one({'bot_id': self.bot.user.id},
                                               {'$set': data})

    async def append_log(self, message: Message,
                         channel_id: Union[int, str] = '',
                         type_: str = 'thread_message'):

        channel_id = str(channel_id) or str(message.channel.id)
        payload = {
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
                'attachments': [i.url for i in message.attachments],
                'type': type_
            }
        
        return await self.logs.find_one_and_update(
            {'channel_id': channel_id},
            {'$push': {f'messages': payload}},
            return_document=ReturnDocument.AFTER
        )

    async def post_log(self, channel_id: Union[int, str], payload: dict):
        return await self.logs.find_one_and_update(
            {'channel_id': str(channel_id)},
            {'$set': {key: payload[key] for key in payload}},
            return_document=ReturnDocument.AFTER
        )

    async def update_repository(self) -> dict:
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

    async def get_user_info(self) -> dict:
        user = await Github.login(self.bot)
        return {
            'user': {
                'username': user.username,
                'avatar_url': user.avatar_url,
                'url': user.url
            }
        }
