import re
from collections import defaultdict
from typing import List

from discord import Embed, Color


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

    def __init__(self, bot, version: str, lines: str):
        self.bot = bot
        self.version = version.lstrip("vV")
        self.lines = [x for x in lines.splitlines() if x]
        self.fields = defaultdict(str)
        self.description = ""
        self.parse()

    def __repr__(self) -> str:
        return f'Version(v{self.version}, description="{self.description}")'

    def parse(self) -> None:
        """
        Parse the lines and split them into `description` and `fields`.
        """
        curr_action = None

        for line in self.lines:
            if line.startswith("### "):
                curr_action = line[4:]
            elif curr_action is None:
                self.description += line + "\n"
            else:
                self.fields[curr_action] += line + "\n"

    @property
    def url(self) -> str:
        return Changelog.CHANGELOG_URL + "#v" + self.version.replace(".", "")

    @property
    def embed(self) -> Embed:
        """
        Embed: the formatted `Embed` of this `Version`.
        """
        embed = Embed(color=Color.green(), description=self.description)
        embed.set_author(
            name=f"v{self.version} - Changelog",
            icon_url=self.bot.user.avatar_url,
            url=self.url,
        )

        for name, value in self.fields.items():
            embed.add_field(name=name, value=value)
        embed.set_footer(text=f"Current version: v{self.bot.version}")
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
    RAW_CHANGELOG_URL : str
        The URL to Modmail changelog.
    CHANGELOG_URL : str
        The URL to Modmail changelog directly from in GitHub.
    VERSION_REGEX : re.Pattern
        The regex used to parse the versions.
    """

    RAW_CHANGELOG_URL = (
        "https://raw.githubusercontent.com/kyb3r/modmail/master/CHANGELOG.md"
    )
    CHANGELOG_URL = "https://github.com/kyb3r/modmail/blob/master/CHANGELOG.md"
    VERSION_REGEX = re.compile(r"# (v\d+\.\d+\.\d+)([\S\s]*?(?=# v|$))")

    def __init__(self, bot, text: str):
        self.bot = bot
        self.text = text
        self.versions = [Version(bot, *m) for m in self.VERSION_REGEX.findall(text)]

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
    async def from_url(cls, bot, url: str = "") -> "Changelog":
        """
        Create a `Changelog` from a URL.

        Parameters
        ----------
        bot : Bot
            The Modmail bot.
        url : str, optional
            Defaults to `RAW_CHANGELOG_URL`.
            The URL to the changelog.

        Returns
        -------
        Changelog
            The newly created `Changelog` parsed from the `url`.
        """
        url = url or cls.RAW_CHANGELOG_URL
        resp = await bot.session.get(url)
        return cls(bot, await resp.text())
