import asyncio
import re
from subprocess import PIPE
from typing import List

from discord import Embed

from core.models import getLogger
from core.utils import truncate

logger = getLogger(__name__)


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

    def __init__(self, bot, branch: str, version: str, lines: str):
        self.bot = bot
        self.version = version.lstrip("vV")
        self.lines = lines.strip()
        self.fields = {}
        self.changelog_url = f"https://github.com/kyb3r/modmail/blob/{branch}/CHANGELOG.md"
        self.description = ""
        self.parse()

    def __repr__(self) -> str:
        return f'Version(v{self.version}, description="{self.description}")'

    def parse(self) -> None:
        """
        Parse the lines and split them into `description` and `fields`.
        """
        self.description = re.match(self.DESCRIPTION_REGEX, self.lines, re.DOTALL)
        self.description = self.description.group(1).strip() if self.description is not None else ""

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
        return f"{self.changelog_url}#v{self.version[::2]}"

    @property
    def embed(self) -> Embed:
        """
        Embed: the formatted `Embed` of this `Version`.
        """
        embed = Embed(color=self.bot.main_color, description=self.description)
        embed.set_author(
            name=f"v{self.version} - Changelog",
            icon_url=self.bot.user.display_avatar.url,
            url=self.url,
        )

        for name, value in self.fields.items():
            embed.add_field(name=name, value=truncate(value, 1024), inline=False)
        embed.set_footer(text=f"Current version: v{self.bot.version}")

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
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
    VERSION_REGEX : re.Pattern
        The regex used to parse the versions.
    """

    VERSION_REGEX = re.compile(
        r"#\s*([vV]\d+\.\d+(?:\.\d+)?(?:-\w+?)?)\s+(.*?)(?=#\s*[vV]\d+\.\d+(?:\.\d+)(?:-\w+?)?|$)",
        flags=re.DOTALL,
    )

    def __init__(self, bot, branch: str, text: str):
        self.bot = bot
        self.text = text
        logger.debug("Fetching changelog from GitHub.")
        self.versions = [Version(bot, branch, *m) for m in self.VERSION_REGEX.findall(text)]

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
            The URL to the changelog.

        Returns
        -------
        Changelog
            The newly created `Changelog` parsed from the `url`.
        """
        # get branch via git cli if available
        proc = await asyncio.create_subprocess_shell(
            "git branch --show-current",
            stderr=PIPE,
            stdout=PIPE,
        )
        err = await proc.stderr.read()
        err = err.decode("utf-8").rstrip()
        res = await proc.stdout.read()
        branch = res.decode("utf-8").rstrip()
        if not branch or err:
            branch = "master" if not bot.version.is_prerelease else "development"

        if branch not in ("master", "development"):
            branch = "master"

        url = url or f"https://raw.githubusercontent.com/kyb3r/modmail/{branch}/CHANGELOG.md"

        async with await bot.session.get(url) as resp:
            return cls(bot, branch, await resp.text())
