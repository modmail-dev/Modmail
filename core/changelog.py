from collections import defaultdict
import re 

import discord

class Version:
    def __init__(self, bot, version, lines):
        self.bot = bot 
        self.version = version
        self.lines = [x for x in lines.splitlines() if x]
        self.fields = defaultdict(str)
        self.description = ''
        self.parse()
    
    def __repr__(self):
        return f'Version({self.version}, description="{self.description}")'
    
    def parse(self):
        curr_action = None 
        for line in self.lines:
            if line.startswith('### '):
                curr_action = line.split('### ')[1]
            elif curr_action is None:
                self.description += line + '\n'
            else:
                self.fields[curr_action] += line + '\n'
    
    @property
    def embed(self):
        em = discord.Embed(color=discord.Color.green(), description=self.description)
        em.set_author(
            name=f'{self.version} - Changelog', 
            icon_url=self.bot.user.avatar_url, 
            url='https://modmail.tk/changelog'
            )
        for name, value in self.fields.items():
            em.add_field(name=name, value=value)
        em.set_footer(text=f'Current version: v{self.bot.version}')
        em.set_thumbnail(url=self.bot.user.avatar_url)
        return em

class ChangeLog:

    changelog_url = 'https://raw.githubusercontent.com/kyb3r/modmail/master/CHANGELOG.md'
    regex = re.compile(r'# (v\d+\.\d+\.\d+)([\S\s]*?(?=# v|$))')

    def __init__(self, bot, text):
        self.bot = bot 
        self.text = text 
        self.versions = [Version(bot, *m) for m in self.regex.findall(text)]

    @property
    def latest_version(self):
        return self.versions[0]
    
    @property
    def embeds(self):
        return [v.embed for v in self.versions]
    
    @classmethod
    async def from_repo(cls, bot, url=None):
        url = url or cls.changelog_url
        resp = await bot.session.get(url)
        return cls(bot, await resp.text())
    
if __name__ == '__main__':
    with open('../CHANGELOG.md') as f:
        changelog = ChangeLog(f.read())
        print(changelog.latest_version)
