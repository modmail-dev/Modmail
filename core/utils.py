from discord import Object
from discord.ext import commands

import typing
from urllib.parse import urlparse


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


def is_image_url(u: str, _=None) -> bool:
    for x in {'.png', '.jpg', '.gif', '.jpeg', '.webp'}:
        if urlparse(u.lower()).path.endswith(x):
            return True
    return False


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
