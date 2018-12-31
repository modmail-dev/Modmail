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

    base = 'https://api.modmail.tk'
    github = base + '/github'
    logs = base + '/logs/key'

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

    def get_log_url(self, user, channel):
        return self.request(self.logs, payload={
            'discord_uid': user.id,
            'channel_id': channel.id,
            'guild_id': self.app.guild_id
        })
