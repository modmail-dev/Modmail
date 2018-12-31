import discord
import secrets

from hashlib import sha256

class ApiClient:
    def __init__(self, app):
        self.app = app 
        self.session = app.session
        self.headers = None
    
    async def request(self, url, method='GET', payload=None):
        async with self.session.request(method, url, headers=self.headers, json=payload) as resp:
            try:
                return await resp.json()
            except:
                return await resp.text()
    

class Github(ApiClient):
    commit_url = 'https://api.github.com/repos/kyb3r/modmail/commits'

    async def get_latest_commits(self, limit=3):
        resp = await self.request(self.commit_url)
        for index in range(limit):
            yield resp[index]


class ModmailApiClient(ApiClient):

    base = 'http://api.example.com'
    github = base + '/github'
    logs = base + '/logs'

    def __init__(self, bot):
        super().__init__(bot)
        self.token = bot.config.get('MODMAIL_API_TOKEN')
        if self.token:
            self.headers = {
                'Authorization': 'Bearer ' + self.token
            }
    
    def get_user_info(self):
        return self.request(self.github + '/userinfo')
    
    def update_repository(self):
        return self.request(self.github + '/update-repository')
    
    def get_metadata(self):
        return self.request(self.base + '/metadata')

    def get_user_logs(self, user_id):
        return self.request(self.logs + '/user/' + str(user_id))

    def get_log(self, channel_id):
        return self.request(self.logs + '/' + str(channel_id))

    def get_log_url(self, recipient, channel, creator):
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

    def append_log(self, message, channel_id=''):
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
                'attachments': [i.url for i in message.attachments]
            }
        }
        return self.request(self.logs + f'/{channel_id}', method='PATCH', payload=payload)

    def post_log(self, channel_id, payload):
        return self.request(self.logs + f'/{channel_id}', method='POST', payload=payload)
