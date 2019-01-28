import re
import typing
from urllib import parse

from discord import Object
from discord.ext import commands


class User(commands.IDConverter):
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


def truncate(text: str, max: int=50) -> str:
    return text[:max-3].strip() + '...' if len(text) > max else text

def format_preview(messages):
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
    return bool(parse_image_url(url))


def parse_image_url(url: str) -> str:
    """Checks if a url leads to an image."""
    types = ['.png', '.jpg', '.gif', '.jpeg', '.webp']
    url = parse.urlsplit(url)

    if any(url.path.lower().endswith(i) for i in types):
        return parse.urlunsplit((*url[:3], 'size=128', url[-1]))
    return ''


def days(day: typing.Union[str, int]) -> str:
    day = int(day)
    if day == 0:
        return '**today**'
    return f'{day} day ago' if day == 1 else f'{day} days ago'


def cleanup_code(content: str) -> str:
    """Automatically removes code blocks from the code."""
    # remove ```py\n```
    if content.startswith('```') and content.endswith('```'):
        return '\n'.join(content.split('\n')[1:-1])

    # remove `foo`
    return content.strip('` \n')


def match_user_id(text: str) -> int:
    match = re.match(r'^User ID: (\d+)$', text)
    if match is not None:
        return int(match.group(1))
    return -1
