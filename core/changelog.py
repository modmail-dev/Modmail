import re
from collections import defaultdict
from typing import List

from discord import Embed, Color

from core.models import Bot


class Version:
    def __init__(self, bot: Bot, version: str, lines: str):
        self.bot = bot
        self.version = version
        self.lines = [x for x in lines.splitlines() if x]
        self.fields = defaultdict(str)
        self.description = ''
        self.parse()

    def __repr__(self) -> str:
        return f'Version({self.version}, description="{self.description}")'

    def parse(self) -> None:
        curr_action = None

        for line in self.lines:
            if line.startswith('### '):
                curr_action = line[4:]
            elif curr_action is None:
                self.description += line + '\n'
            else:
                self.fields[curr_action] += line + '\n'

    @property
    def embed(self) -> Embed:
        embed = Embed(color=Color.green(), description=self.description)
        embed.set_author(
            name=f'{self.version} - Changelog',
            icon_url=self.bot.user.avatar_url,
            url='https://modmail.tk/changelog'
        )

        for name, value in self.fields.items():
            embed.add_field(name=name, value=value)
        embed.set_footer(text=f'Current version: v{self.bot.version}')
        embed.set_thumbnail(url=self.bot.user.avatar_url)
        return embed


class ChangeLog:
    changelog_url = ('https://raw.githubusercontent.com/'
                     'kyb3r/modmail/master/CHANGELOG.md')
    regex = re.compile(r'# (v\d+\.\d+\.\d+)([\S\s]*?(?=# v|$))')

    def __init__(self, bot: Bot, text: str):
        self.bot = bot
        self.text = text
        self.versions = [Version(bot, *m) for m in self.regex.findall(text)]

    @property
    def latest_version(self) -> Version:
        return self.versions[0]

    @property
    def embeds(self) -> List[Embed]:
        return [v.embed for v in self.versions]

    @classmethod
    async def from_repo(cls, bot, url: str = '') -> 'ChangeLog':
        url = url or cls.changelog_url
        resp = await bot.session.get(url)
        return cls(bot, await resp.text())


if __name__ == '__main__':
    with open('../CHANGELOG.md') as f:
        print(ChangeLog(..., f.read()).latest_version)
