import re
import typing
from urllib import parse

from discord import Object
from discord.ext import commands

from colorama import Fore, Style


def info(*msgs):
    return f'{Fore.CYAN}{" ".join(msgs)}{Style.RESET_ALL}'


def error(*msgs):
    return f'{Fore.RED}{" ".join(msgs)}{Style.RESET_ALL}'


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
        return Object(int(match.group(1)))


def truncate(text: str, max: int = 50) -> str:
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
    return text[:max-3].strip() + '...' if len(text) > max else text


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
    out = ''
    for message in messages:
        if message.get('type') in ('note', 'internal'):
            continue
        author = message['author']
        content = message['content'].replace('\n', ' ')
        name = author['name'] + '#' + str(author['discriminator'])
        prefix = '[M]' if author['mod'] else '[R]'
        out += truncate(f'`{prefix} {name}:` {content}', max=75) + '\n'

    return out or 'No Messages'


def is_image_url(url: str, _=None) -> bool:
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
    types = ['.png', '.jpg', '.gif', '.jpeg', '.webp']
    url = parse.urlsplit(url)

    if any(url.path.lower().endswith(i) for i in types):
        return parse.urlunsplit((*url[:3], 'size=128', url[-1]))
    return ''


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
        return '**today**'
    return f'{day} day ago' if day == 1 else f'{day} days ago'


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
    if content.startswith('```') and content.endswith('```'):
        return '\n'.join(content.split('\n')[1:-1])

    # remove `foo`
    return content.strip('` \n')


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
    match = re.match(r'^User ID: (\d+)$', text)
    if match is not None:
        return int(match.group(1))
    return -1


async def ignore(coro):
    try:
        await coro
    except Exception:
        pass
