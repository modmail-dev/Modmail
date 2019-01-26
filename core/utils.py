from discord import Object
from discord.ext import commands

import re
import typing
from urllib import parse


class User(commands.IDConverter):
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


def truncate(c: str) -> str:
    return c[:47].strip() + '...' if len(c) > 50 else c


def is_image_url(url: str, _=None) -> bool:
    return bool(parse_image_url(url))


def parse_image_url(url: str) -> str:
    """Checks if a url leads to an image."""
    types = ['.png', '.jpg', '.gif', '.jpeg', '.webp']
    url = parse.urlsplit(url)

    if any(url.path.lower().endswith(i) for i in types):
        return parse.urlunsplit((*url[:3], 'size=128', url[-1]))
    return ''


def days(d: typing.Union[str, int]) -> str:
    d = int(d)
    if d == 0:
        return '**today**'
    return f'{d} day ago' if d == 1 else f'{d} days ago'


def cleanup_code(content: str) -> str:
    """Automatically removes code blocks from the code."""
    # remove ```py\n```
    if content.startswith('```') and content.endswith('```'):
        return '\n'.join(content.split('\n')[1:-1])

    # remove `foo`
    return content.strip('` \n')


def match_user_id(s: str) -> typing.Optional[int]:
    match = re.match(r'^User ID: (\d+)$', s)
    if match is not None:
        return int(match.group(1))
