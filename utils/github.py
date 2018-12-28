class Github:
    head = 'https://api.github.com/repos/kyb3r/modmail/git/refs/heads/master'
    merge_url = 'https://api.github.com/repos/{username}/modmail/merges'
    commit_url = 'https://api.github.com/repos/kyb3r/modmail/commits'

    def __init__(self, app, access_token=None, username=None):
        self.app = app
        self.session = app.session
        self.access_token = access_token
        self.username = username
        self.avatar_url = None
        self.url = None
        self.headers = None
        if self.access_token:
            self.headers = {'Authorization': 'token ' + str(access_token)}

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

    async def request(self, url, method='GET', payload=None):
        async with self.session.request(method, url, headers=self.headers, json=payload) as resp:
            try:
                return await resp.json()
            except:
                return await resp.text()

    @classmethod
    async def login(cls, bot, access_token):
        self = cls(bot, access_token)
        resp = await self.request('https://api.github.com/user')
        self.username = resp['login']
        self.avatar_url = resp['avatar_url']
        self.url = resp['html_url']
        return self
