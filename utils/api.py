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
    head = 'https://api.github.com/repos/kyb3r/modmail/git/refs/heads/master'
    merge_url = 'https://api.github.com/repos/{username}/modmail/merges'
    commit_url = 'https://api.github.com/repos/kyb3r/modmail/commits'

    def __init__(self, app, access_token=None):
        super().__init__(app)
        self.username = None
        self.avatar_url = None
        self.url = None
        self.headers = None
        if access_token:
            self.headers = {'Authorization': 'token ' + str(access_token)}

    @classmethod
    async def login(cls, bot, access_token):
        self = cls(bot, access_token)
        resp = await self.request('https://api.github.com/user')
        self.username = resp['login']
        self.avatar_url = resp['avatar_url']
        self.url = resp['html_url']
        return self

    async def get_latest_commits(self, limit=3):
        resp = await self.request(self.commit_url)
        for index in range(limit):
            yield resp[index]

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

class ModmailApiClient(ApiClient):

    base = 'https://api.kybr.tk/modmail'
    github = base + '/github'

    def __init__(self, bot):
        super().__init__(bot)
        self.token = str(sha256(bot.token.encode()).hexdigest()) # added security
        self.headers = {
            'Authorization': 'Bearer ' + self.token
        }
    
    def get_user_info(self):
        return self.request(self.github + '/userinfo')
    
    def update_repository(self):
        return self.request(self.github + '/update-repository')
    
    def logout(self):
        return self.request(self.github + '/logout')
    
    def get_metadata(self):
        return self.request(self.base)
