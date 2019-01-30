import re
from collections import defaultdict
from typing import List

from discord import Embed, Color

from core.models import Bot


class Version:
    """
    This class represents a single version of Modmail.

    Parameters
    ----------
    bot : Bot
        The Modmail bot.
    version : str
        The version string (ie. "v2.12.0").
    lines : str
        The lines of changelog messages for this version.

    Attributes
    ----------
    bot : Bot
        The Modmail bot.
    version : str
        The version string (ie. "v2.12.0").
    lines : List[str]
        A list of lines of changelog messages for this version.
    fields : defaultdict[str, str]
        A dict of fields separated by "Fixed", "Changed", etc sections.
    description : str
        General description of the version.
    """

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
        """
        Parse the lines and split them into `description` and `fields`.
        """
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
        """
        Embed: the formatted `Embed` of this `Version`.
        """
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


class Changelog:
    """
    This class represents the complete changelog of Modmail.

    Parameters
    ----------
    bot : Bot
        The Modmail bot.
    text : str
        The complete changelog text.

    Attributes
    ----------
    bot : Bot
        The Modmail bot.
    text : str
        The complete changelog text.
    versions : List[Version]
        A list of `Version`'s within the changelog.

    Class Attributes
    ----------------
    CHANGELOG_URL : str
        The URL to Modmail changelog.
    VERSION_REGEX : re.Pattern
        The regex used to parse the versions.
    """

    CHANGELOG_URL = ('https://raw.githubusercontent.com/'
                     'kyb3r/modmail/master/CHANGELOG.md')
    VERSION_REGEX = re.compile(r'# (v\d+\.\d+\.\d+)([\S\s]*?(?=# v|$))')

    def __init__(self, bot: Bot, text: str):
        self.bot = bot
        self.text = text
        self.versions = [Version(bot, *m)
                         for m in self.VERSION_REGEX.findall(text)]

    @property
    def latest_version(self) -> Version:
        """
        Version: The latest `Version` of the `Changelog`.
        """
        return self.versions[0]

    @property
    def embeds(self) -> List[Embed]:
        """
        List[Embed]: A list of `Embed`'s for each of the `Version`.
        """
        return [v.embed for v in self.versions]

    @classmethod
    async def from_url(cls, bot: Bot, url: str = '') -> 'Changelog':
        """
        Create a `Changelog` from a URL.

        Parameters
        ----------
        bot : Bot
            The Modmail bot.
        url : str, optional
            Defaults to `CHANGELOG_URL`.
            The URL to the changelog.

        Returns
        -------
        Changelog
            The newly created `Changelog` parsed from the `url`.
        """
        url = url or cls.CHANGELOG_URL
        resp = await bot.session.get(url)
        return cls(bot, await resp.text())


if __name__ == '__main__':
    with open('../CHANGELOG.md') as f:
        print(Changelog(..., f.read()).latest_version)
