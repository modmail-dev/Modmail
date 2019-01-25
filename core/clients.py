import discord
import secrets
from datetime import datetime

from pymongo import ReturnDocument


class ApiClient:
    def __init__(self, app):
        self.app = app
        self.session = app.session
        self.headers = None

    async def request(self, url, method='GET', payload=None, return_response=False):
        async with self.session.request(method, url, headers=self.headers, json=payload) as resp:
            if return_response:
                return resp
            try:
                return await resp.json()
            except:
                return await resp.text()

class Github(ApiClient):
    BASE = 'https://api.github.com'
    REPO = BASE + '/repos/kyb3r/modmail'
    head = REPO + '/git/refs/heads/master'
    merge_url = BASE + '/repos/{username}/modmail/merges'
    fork_url = REPO + '/forks'
    star_url = BASE + '/user/starred/kyb3r/modmail'

    def __init__(self, app, access_token=None, username=None):
        self.app = app
        self.session = app.session
        self.access_token = access_token
        self.username = username
        self.id = None
        self.avatar_url = None
        self.url = None
        self.headers = None
        if self.access_token:
            self.headers = {'Authorization': 'token ' + str(access_token)}

    async def update_repository(self, sha=None):
        if sha is None:
            resp = await self.request(self.head)
            sha = resp['object']['sha']

        payload = {
            'base': 'master',
            'head': sha,
            'commit_message': 'Updating bot'
        }

        merge_url = self.merge_url.format(username=self.username)

        resp = await self.request(merge_url, method='POST', payload=payload)
        if isinstance(resp, dict):
            return resp

    async def fork_repository(self):
        await self.request(self.fork_url, method='POST')
    
    async def has_starred(self):
        resp = await self.request(self.star_url, return_response=True)
        return resp.status == 204

    async def star_repository(self):
        await self.request(self.star_url, method='PUT', headers={'Content-Length':  '0'})

    async def get_latest_commits(self, limit=3):
        resp = await self.request(self.commit_url)
        for index in range(limit):
            yield resp[index]

    @classmethod
    async def login(cls, bot):
        self = cls(bot, bot.config.get('github_access_token'))
        resp = await self.request('https://api.github.com/user')
        self.username = resp['login']
        self.avatar_url = resp['avatar_url']
        self.url = resp['html_url']
        self.id = resp['id']
        self.raw_data = resp
        print(f'Logged in to: {self.username} - {self.id}')
        return self


class ModmailApiClient(ApiClient):

    base = 'https://api.modmail.tk'
    metadata = base + '/metadata'
    github = base + '/github'
    logs = base + '/logs'
    config = base + '/config'

    def __init__(self, bot):
        super().__init__(bot)
        self.token = bot.config.get('modmail_api_token')
        if self.token:
            self.headers = {
                'Authorization': 'Bearer ' + self.token
            }

    async def validate_token(self):
        resp = await self.request(self.base + '/token/verify', return_response=True)
        return resp.status == 200

    def post_metadata(self, data):
        return self.request(self.metadata, method='POST', payload=data)

    def get_user_info(self):
        return self.request(self.github + '/userinfo')

    def update_repository(self):
        return self.request(self.github + '/update')

    def get_metadata(self):
        return self.request(self.base + '/metadata')

    def get_user_logs(self, user_id):
        return self.request(self.logs + '/user/' + str(user_id))

    def get_log(self, channel_id):
        return self.request(self.logs + '/' + str(channel_id))
    
    async def get_log_link(self, channel_id):
        doc = await self.get_log(channel_id)
        return f'https://logs.modmail.tk/{doc["key"]}'

    def get_config(self):
        return self.request(self.config)

    def update_config(self, data):
        valid_keys = self.app.config.valid_keys - self.app.config.protected_keys
        data = {k: v for k, v in data.items() if k in valid_keys}
        return self.request(self.config, method='PATCH', payload=data)

    def create_log_entry(self, recipient, channel, creator):
        return self.request(self.logs + '/key', payload={
            'channel_id': str(channel.id),
            'guild_id': str(self.app.guild_id),
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
                'mod': isinstance(creator, discord.Member)
            }
        })

    async def edit_message(self, message_id, new_content):
        return await self.request(self.logs + '/edit', method='PATCH', payload={
            'message_id': str(message_id),
            'new_content':  new_content
        })

    def append_log(self, message, channel_id='', type='thread_message'):
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
                    'mod': not isinstance(message.channel, discord.DMChannel),
                },
                # message properties
                'content': message.content,
                'type': type,
                'attachments': [
                    {   
                        'id': a.id,
                        'filename': a.filename,
                        'is_image': a.width is not None,
                        'size': a.size,
                        'url': a.url 
                    } for a in message.attachments ]
            }
        }
        return self.request(self.logs + f'/{channel_id}', method='PATCH', payload=payload)

    def post_log(self, channel_id, payload):
        return self.request(self.logs + f'/{channel_id}', method='POST', payload=payload)


class SelfhostedClient(ModmailApiClient):

    def __init__(self, bot):
        super().__init__(bot)
        self.token = bot.config.get('github_access_token')
        if self.token:
            self.headers = {
                'Authorization': 'Bearer ' + self.token
            }

    @property
    def db(self):
        return self.app.db 
    
    @property 
    def logs(self):
        return self.db.logs

    async def get_user_logs(self, user_id):
        logs = []

        async for entry in self.logs.find({'recipient.id': str(user_id)}):
            logs.append(entry)

        return logs

    async def get_log(self, channel_id):
        return await self.logs.find_one({'channel_id': str(channel_id)})
    
    async def get_log_link(self, channel_id):
        doc = await self.get_log(channel_id)
        key = doc['key']
        return f"{self.app.config.log_url.strip('/')}/logs/{key}"

    async def create_log_entry(self, recipient, channel, creator):
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
                'mod': isinstance(creator, discord.Member)
            },
            'closer': None,
            'messages': []
        })

        return f"{self.app.config.log_url.strip('/')}/logs/{key}"

    async def get_config(self):
        conf = await self.db.config.find_one({'bot_id': self.app.user.id})
        if conf is None:
            await self.db.config.insert_one({'bot_id': self.app.user.id})
            return {'bot_id': self.app.user.id}
        return conf

    async def update_config(self, data):
        valid_keys = self.app.config.valid_keys - self.app.config.protected_keys
        data = {k: v for k, v in data.items() if k in valid_keys}
        return await self.db.config.update_one({'bot_id': self.app.user.id}, {'$set': data})
    
    async def edit_message(self, message_id, new_content):
        await self.logs.update_one(
            {'messages.message_id': str(message_id)},
            {'$set': {
                'messages.$.content': new_content,
                'messages.$.edited': True
                }
            })

    async def append_log(self, message, channel_id='', type='thread_message'):
        channel_id = str(channel_id) or str(message.channel.id)
        payload = {
                'timestamp': str(message.created_at),
                'message_id': str(message.id),
                'author': {
                    'id': str(message.author.id),
                    'name': message.author.name,
                    'discriminator': message.author.discriminator,
                    'avatar_url': message.author.avatar_url,
                    'mod': not isinstance(message.channel, discord.DMChannel),
                },
                'content': message.content,
                'type': type,
                'attachments': [
                    {   
                        'id': a.id,
                        'filename': a.filename,
                        'is_image': a.width is not None,
                        'size': a.size,
                        'url': a.url 
                    } for a in message.attachments ]
            }
        
        return await self.logs.find_one_and_update(
            {'channel_id': channel_id},
            {'$push': {f'messages': payload}},
            return_document=ReturnDocument.AFTER
        )

    async def post_log(self, channel_id, payload):
        log = await self.logs.find_one_and_update(
            {'channel_id': str(channel_id)},
            {'$set': {key: payload[key] for key in payload}},
            return_document=ReturnDocument.AFTER
        )
        return log

    async def update_repository(self):
        user = await Github.login(self.app)
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
        user = await Github.login(self.app)
        return {
            'user': {
                'username': user.username,
                'avatar_url': user.avatar_url,
                'url': user.url
            }
        }