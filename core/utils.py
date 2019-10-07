import functools
import re
import shlex
import typing
from difflib import get_close_matches
from distutils.util import strtobool as _stb  # pylint: disable=import-error
from itertools import takewhile
from urllib import parse

import discord
from discord.ext import commands


def strtobool(val):
    if isinstance(val, bool):
        return val
    return _stb(str(val))


class User(commands.IDConverter):
    """
    A custom discord.py `Converter` that
    supports `Member`, `User`, and string ID's.
    """

    # noinspection PyCallByClass,PyTypeChecker
    async def convert(self, ctx, argument):
        try:
            return await commands.MemberConverter.convert(self, ctx, argument)
        except commands.BadArgument:
            pass
        try:
            return await commands.UserConverter.convert(self, ctx, argument)
        except commands.BadArgument:
            pass
        match = self._get_id_match(argument)
        if match is None:
            raise commands.BadArgument('User "{}" not found'.format(argument))
        return discord.Object(int(match.group(1)))


def truncate(text: str, max: int = 50) -> str:  # pylint: disable=redefined-builtin
    """
    Reduces the string to `max` length, by trimming the message into "...".

    Parameters
    ----------
    text : str
        The text to trim.
    max : int, optional
        The max length of the text.
        Defaults to 50.

    Returns
    -------
    str
        The truncated text.
    """
    text = text.strip()
    return text[: max - 3].strip() + "..." if len(text) > max else text


def format_preview(messages: typing.List[typing.Dict[str, typing.Any]]):
    """
    Used to format previews.

    Parameters
    ----------
    messages : List[Dict[str, Any]]
        A list of messages.

    Returns
    -------
    str
        A formatted string preview.
    """
    messages = messages[:3]
    out = ""
    for message in messages:
        if message.get("type") in {"note", "internal"}:
            continue
        author = message["author"]
        content = str(message["content"]).replace("\n", " ")
        name = author["name"] + "#" + str(author["discriminator"])
        prefix = "[M]" if author["mod"] else "[R]"
        out += truncate(f"`{prefix} {name}:` {content}", max=75) + "\n"

    return out or "No Messages"


def is_image_url(url: str) -> bool:
    """
    Check if the URL is pointing to an image.

    Parameters
    ----------
    url : str
        The URL to check.

    Returns
    -------
    bool
        Whether the URL is a valid image URL.
    """
    return bool(parse_image_url(url))


def parse_image_url(url: str) -> str:
    """
    Convert the image URL into a sized Discord avatar.

    Parameters
    ----------
    url : str
        The URL to convert.

    Returns
    -------
    str
        The converted URL, or '' if the URL isn't in the proper format.
    """
    types = [".png", ".jpg", ".gif", ".jpeg", ".webp"]
    url = parse.urlsplit(url)

    if any(url.path.lower().endswith(i) for i in types):
        return parse.urlunsplit((*url[:3], "size=128", url[-1]))
    return ""


def human_join(strings):
    if len(strings) <= 2:
        return " or ".join(strings)
    return ", ".join(strings[: len(strings) - 1]) + " or " + strings[-1]


def days(day: typing.Union[str, int]) -> str:
    """
    Humanize the number of days.

    Parameters
    ----------
    day: Union[int, str]
        The number of days passed.

    Returns
    -------
    str
        A formatted string of the number of days passed.
    """
    day = int(day)
    if day == 0:
        return "**today**"
    return f"{day} day ago" if day == 1 else f"{day} days ago"


def cleanup_code(content: str) -> str:
    """
    Automatically removes code blocks from the code.

    Parameters
    ----------
    content : str
        The content to be cleaned.

    Returns
    -------
    str
        The cleaned content.
    """
    # remove ```py\n```
    if content.startswith("```") and content.endswith("```"):
        return "\n".join(content.split("\n")[1:-1])

    # remove `foo`
    return content.strip("` \n")


def match_user_id(text: str) -> int:
    """
    Matches a user ID in the format of "User ID: 12345".

    Parameters
    ----------
    text : str
        The text of the user ID.

    Returns
    -------
    int
        The user ID if found. Otherwise, -1.
    """
    match = re.search(r"\bUser ID: (\d{17,21})\b", text)
    if match is not None:
        return int(match.group(1))
    return -1


def create_not_found_embed(word, possibilities, name, n=2, cutoff=0.6) -> discord.Embed:
    # Single reference of Color.red()
    embed = discord.Embed(
        color=discord.Color.red(),
        description=f"**{name.capitalize()} `{word}` cannot be found.**",
    )
    val = get_close_matches(word, possibilities, n=n, cutoff=cutoff)
    if val:
        embed.description += "\nHowever, perhaps you meant...\n" + "\n".join(val)
    return embed


def parse_alias(alias):
    if "&&" not in alias:
        if alias.startswith('"') and alias.endswith('"'):
            return [alias[1:-1]]
        return [alias]

    buffer = ""
    cmd = []
    try:
        for token in shlex.shlex(alias, punctuation_chars="&"):
            if token != "&&":
                buffer += " " + token
                continue

            buffer = buffer.strip()
            if buffer.startswith('"') and buffer.endswith('"'):
                buffer = buffer[1:-1]
            cmd += [buffer]
            buffer = ""
    except ValueError:
        return []

    buffer = buffer.strip()
    if buffer.startswith('"') and buffer.endswith('"'):
        buffer = buffer[1:-1]
    cmd += [buffer]

    if not all(cmd):
        return []
    return cmd


def format_description(i, names):
    return "\n".join(
        ": ".join((str(a + i * 15), b))
        for a, b in enumerate(takewhile(lambda x: x is not None, names), start=1)
    )


def trigger_typing(func):
    @functools.wraps(func)
    async def wrapper(self, ctx: commands.Context, *args, **kwargs):
        await ctx.trigger_typing()
        return await func(self, ctx, *args, **kwargs)

    return wrapper
