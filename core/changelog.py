import logging
import re
from typing import List

from discord import Embed

from core.utils import truncate

logger = logging.getLogger("Modmail")


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
    lines : str
        A list of lines of changelog messages for this version.
    fields : Dict[str, str]
        A dict of fields separated by "Fixed", "Changed", etc sections.
    description : str
        General description of the version.

    Class Attributes
    ----------------
    ACTION_REGEX : str
        The regex used to parse the actions.
    DESCRIPTION_REGEX: str
        The regex used to parse the description.
    """

    ACTION_REGEX = r"###\s*(.+?)\s*\n(.*?)(?=###\s*.+?|$)"
    DESCRIPTION_REGEX = r"^(.*?)(?=###\s*.+?|$)"

    def __init__(self, bot, version: str, lines: str):
        self.bot = bot
        self.version = version.lstrip("vV")
        self.lines = lines.strip()
        self.fields = {}
        self.description = ""
        self.parse()

    def __repr__(self) -> str:
        return f'Version(v{self.version}, description="{self.description}")'

    def parse(self) -> None:
        """
        Parse the lines and split them into `description` and `fields`.
        """
        self.description = re.match(self.DESCRIPTION_REGEX, self.lines, re.DOTALL)
        self.description = (
            self.description.group(1).strip() if self.description is not None else ""
        )

        matches = re.finditer(self.ACTION_REGEX, self.lines, re.DOTALL)
        for m in matches:
            try:
                self.fields[m.group(1).strip()] = m.group(2).strip()
            except AttributeError:
                logger.error(
                    "Something went wrong when parsing the changelog for version %s.",
                    self.version,
                    exc_info=True,
                )

    @property
    def url(self) -> str:
        return f"{Changelog.CHANGELOG_URL}#v{self.version[::2]}"

    @property
    def embed(self) -> Embed:
        """
        Embed: the formatted `Embed` of this `Version`.
        """
        embed = Embed(color=self.bot.main_color, description=self.description)
        embed.set_author(
            name=f"v{self.version} - Changelog",
            icon_url=self.bot.user.avatar_url,
            url=self.url,
        )

        for name, value in self.fields.items():
            embed.add_field(name=name, value=truncate(value, 1024))
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
    VERSION_REGEX = re.compile(
        r"#\s*([vV]\d+\.\d+(?:\.\d+)?)\s+(.*?)(?=#\s*[vV]\d+\.\d+(?:\.\d+)?|$)",
        flags=re.DOTALL,
    )

    def __init__(self, bot, text: str):
        self.bot = bot
        self.text = text
        logger.debug("Fetching changelog from GitHub.")
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
