class Github:
    head = 'https://api.github.com/repos/kyb3r/modmail/git/refs/heads/master'
    merge_url = 'https://api.github.com/repos/{username}/modmail/merges'

    def __init__(self, bot, access_token, username=None):
        self.bot = bot
        self.session = bot.session
        self.access_token = access_token
        self.username = username
        self.headers = {'Authorization': 'Bearer '+access_token}
    
    async def update_repository(self):
        sha = (await self.request(self.head))['object']['sha']
        payload = {
            'base': 'master',
            'head': sha,
            'commit_message': 'Updating bot'
        }
        merge_url = self.merge_url.format(username=self.username)

        r = await self.request(merge_url, method='POST', payload=payload)
        if isinstance(r, dict):
            return r['html_url']

    async def request(self, url, method='GET', payload=None):
        async with self.session.request(method, url, headers=self.headers, json=payload) as resp:
            try:
                return await resp.json()
            except:
                return await resp.text()
    
    @classmethod
    async def login(cls, bot, access_token):
        self = cls(bot, access_token)
        self.username = (await self.request('https://api.github.com/user'))['login']
        return self