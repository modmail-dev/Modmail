import base64
import functools
import re
import typing
from datetime import datetime, timezone
from difflib import get_close_matches
from distutils.util import strtobool as _stb  # pylint: disable=import-error
from itertools import takewhile, zip_longest
from urllib import parse

import discord
from discord.ext import commands

from core.models import getLogger


__all__ = [
    "strtobool",
    "User",
    "truncate",
    "format_preview",
    "is_image_url",
    "parse_image_url",
    "human_join",
    "days",
    "cleanup_code",
    "parse_channel_topic",
    "match_title",
    "match_user_id",
    "match_other_recipients",
    "create_thread_channel",
    "create_not_found_embed",
    "parse_alias",
    "normalize_alias",
    "format_description",
    "trigger_typing",
    "escape_code_block",
    "tryint",
    "get_top_role",
    "get_joint_id",
    "extract_block_timestamp",
]


logger = getLogger(__name__)


def strtobool(val):
    if isinstance(val, bool):
        return val
    try:
        return _stb(str(val))
    except ValueError:
        val = val.lower()
        if val == "enable":
            return 1
        if val == "disable":
            return 0
        raise


class User(commands.MemberConverter):
    """
    A custom discord.py `Converter` that
    supports `Member`, `User`, and string ID's.
    """

    # noinspection PyCallByClass,PyTypeChecker
    async def convert(self, ctx, argument):
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            pass
        try:
            return await commands.UserConverter().convert(ctx, argument)
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


def is_image_url(url: str, **kwargs) -> str:
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
    if url.startswith("https://gyazo.com") or url.startswith("http://gyazo.com"):
        # gyazo support
        url = re.sub(
            r"(http[s]?:\/\/)((?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)",
            r"\1i.\2.png",
            url,
        )

    return parse_image_url(url, **kwargs)


def parse_image_url(url: str, *, convert_size=True) -> str:
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
        if convert_size:
            return parse.urlunsplit((*url[:3], "size=128", url[-1]))
        else:
            return parse.urlunsplit(url)
    return ""


def human_join(seq: typing.Sequence[str], delim: str = ", ", final: str = "or") -> str:
    """https://github.com/Rapptz/RoboDanny/blob/bf7d4226350dff26df4981dd53134eeb2aceeb87/cogs/utils/formats.py#L21-L32"""
    size = len(seq)
    if size == 0:
        return ""

    if size == 1:
        return seq[0]

    if size == 2:
        return f"{seq[0]} {final} {seq[1]}"

    return delim.join(seq[:-1]) + f" {final} {seq[-1]}"


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


TOPIC_REGEX = re.compile(
    r"(?:\bTitle:\s*(?P<title>.*)\n)?"
    r"\bUser ID:\s*(?P<user_id>\d{17,21})\b"
    r"(?:\nOther Recipients:\s*(?P<other_ids>\d{17,21}(?:(?:\s*,\s*)\d{17,21})*)\b)?",
    flags=re.IGNORECASE | re.DOTALL,
)
UID_REGEX = re.compile(r"\bUser ID:\s*(\d{17,21})\b", flags=re.IGNORECASE)


def parse_channel_topic(text: str) -> typing.Tuple[typing.Optional[str], int, typing.List[int]]:
    """
    A helper to parse channel topics and respectivefully returns all the required values
    at once.

    Parameters
    ----------
    text : str
        The text of channel topic.

    Returns
    -------
    Tuple[Optional[str], int, List[int]]
        A tuple of title, user ID, and other recipients IDs.
    """
    title, user_id, other_ids = None, -1, []
    if isinstance(text, str):
        match = TOPIC_REGEX.search(text)
    else:
        match = None

    if match is not None:
        groupdict = match.groupdict()
        title = groupdict["title"]

        # user ID string is the required one in regex, so if match is found
        # the value of this won't be None
        user_id = int(groupdict["user_id"])

        oth_ids = groupdict["other_ids"]
        if oth_ids:
            other_ids = list(map(int, oth_ids.split(",")))

    return title, user_id, other_ids


def match_title(text: str) -> str:
    """
    Matches a title in the format of "Title: XXXX"

    Parameters
    ----------
    text : str
        The text of the user ID.

    Returns
    -------
    Optional[str]
        The title if found.
    """
    return parse_channel_topic(text)[0]


def match_user_id(text: str, any_string: bool = False) -> int:
    """
    Matches a user ID in the format of "User ID: 12345".

    Parameters
    ----------
    text : str
        The text of the user ID.
    any_string: bool
        Whether to search any string that matches the UID_REGEX, e.g. not from channel topic.
        Defaults to False.

    Returns
    -------
    int
        The user ID if found. Otherwise, -1.
    """
    user_id = -1
    if any_string:
        match = UID_REGEX.search(text)
        if match is not None:
            user_id = int(match.group(1))
    else:
        user_id = parse_channel_topic(text)[1]

    return user_id


def match_other_recipients(text: str) -> typing.List[int]:
    """
    Matches a title in the format of "Other Recipients: XXXX,XXXX"

    Parameters
    ----------
    text : str
        The text of the user ID.

    Returns
    -------
    List[int]
        The list of other recipients IDs.
    """
    return parse_channel_topic(text)[2]


def create_not_found_embed(word, possibilities, name, n=2, cutoff=0.6) -> discord.Embed:
    # Single reference of Color.red()
    embed = discord.Embed(
        color=discord.Color.red(), description=f"**{name.capitalize()} `{word}` cannot be found.**"
    )
    val = get_close_matches(word, possibilities, n=n, cutoff=cutoff)
    if val:
        embed.description += "\nHowever, perhaps you meant...\n" + "\n".join(val)
    return embed


def parse_alias(alias, *, split=True):
    def encode_alias(m):
        return "\x1AU" + base64.b64encode(m.group(1).encode()).decode() + "\x1AU"

    def decode_alias(m):
        return base64.b64decode(m.group(1).encode()).decode()

    alias = re.sub(
        r"(?:(?<=^)(?:\s*(?<!\\)(?:\")\s*)|(?<=&&)(?:\s*(?<!\\)(?:\")\s*))(.+?)"
        r"(?:(?:\s*(?<!\\)(?:\")\s*)(?=&&)|(?:\s*(?<!\\)(?:\")\s*)(?=$))",
        encode_alias,
        alias,
    ).strip()

    aliases = []
    if not alias:
        return aliases

    if split:
        iterate = re.split(r"\s*&&\s*", alias)
    else:
        iterate = [alias]

    for a in iterate:
        a = re.sub("\x1AU(.+?)\x1AU", decode_alias, a)
        if a[0] == a[-1] == '"':
            a = a[1:-1]
        aliases.append(a)

    return aliases


def normalize_alias(alias, message=""):
    aliases = parse_alias(alias)
    contents = parse_alias(message, split=False)

    final_aliases = []
    for a, content in zip_longest(aliases, contents):
        if a is None:
            break

        if content:
            final_aliases.append(f"{a} {content}")
        else:
            final_aliases.append(a)

    return final_aliases


def format_description(i, names):
    return "\n".join(
        ": ".join((str(a + i * 15), b))
        for a, b in enumerate(takewhile(lambda x: x is not None, names), start=1)
    )


def trigger_typing(func):
    @functools.wraps(func)
    async def wrapper(self, ctx: commands.Context, *args, **kwargs):
        await ctx.typing()
        return await func(self, ctx, *args, **kwargs)

    return wrapper


def escape_code_block(text):
    return re.sub(r"```", "`\u200b``", text)


def tryint(x):
    try:
        return int(x)
    except (ValueError, TypeError):
        return x


def get_top_role(member: discord.Member, hoisted=True):
    roles = sorted(member.roles, key=lambda r: r.position, reverse=True)
    for role in roles:
        if not hoisted:
            return role
        if role.hoist:
            return role


async def create_thread_channel(bot, recipient, category, overwrites, *, name=None, errors_raised=None):
    name = name or bot.format_channel_name(recipient)
    errors_raised = errors_raised or []

    try:
        channel = await bot.modmail_guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            topic=f"User ID: {recipient.id}",
            reason="Creating a thread channel.",
        )
    except discord.HTTPException as e:
        if (e.text, (category, name)) in errors_raised:
            # Just raise the error to prevent infinite recursion after retrying
            raise

        errors_raised.append((e.text, (category, name)))

        if "Maximum number of channels in category reached" in e.text:
            fallback = None
            fallback_id = bot.config["fallback_category_id"]
            if fallback_id:
                fallback = discord.utils.get(category.guild.categories, id=int(fallback_id))
                if fallback and len(fallback.channels) >= 49:
                    fallback = None

            if not fallback:
                fallback = await category.clone(name="Fallback Modmail")
                await bot.config.set("fallback_category_id", str(fallback.id))
                await bot.config.update()

            return await create_thread_channel(
                bot, recipient, fallback, overwrites, errors_raised=errors_raised
            )

        if "Contains words not allowed" in e.text:
            # try again but null-discrim (name could be banned)
            return await create_thread_channel(
                bot,
                recipient,
                category,
                overwrites,
                name=bot.format_channel_name(recipient, force_null=True),
                errors_raised=errors_raised,
            )

        raise

    return channel


def get_joint_id(message: discord.Message) -> typing.Optional[int]:
    """
    Get the joint ID from `discord.Embed().author.url`.
    Parameters
    -----------
    message : discord.Message
        The discord.Message object.
    Returns
    -------
    int
        The joint ID if found. Otherwise, None.
    """
    if message.embeds:
        try:
            url = getattr(message.embeds[0].author, "url", "")
            if url:
                return int(url.split("#")[-1])
        except ValueError:
            pass
    return None


def extract_block_timestamp(reason, id_):
    # etc "blah blah blah... until <t:XX:f>."
    now = discord.utils.utcnow()
    end_time = re.search(r"until <t:(\d+):(?:R|f)>.$", reason)
    attempts = [
        # backwards compat
        re.search(r"until ([^`]+?)\.$", reason),
        re.search(r"%([^%]+?)%", reason),
    ]
    after = None
    if end_time is None:
        for i in attempts:
            if i is not None:
                end_time = i
                break

        if end_time is not None:
            # found a deprecated version
            try:
                after = (
                    datetime.fromisoformat(end_time.group(1)).replace(tzinfo=timezone.utc) - now
                ).total_seconds()
            except ValueError:
                logger.warning(
                    r"Broken block message for user %s, block and unblock again with a different message to prevent further issues",
                    id_,
                )
                raise
            logger.warning(
                r"Deprecated time message for user %s, block and unblock again to update.",
                id_,
            )
    else:
        try:
            after = (
                datetime.utcfromtimestamp(int(end_time.group(1))).replace(tzinfo=timezone.utc) - now
            ).total_seconds()
        except ValueError:
            logger.warning(
                r"Broken block message for user %s, block and unblock again with a different message to prevent further issues",
                id_,
            )
            raise

    return end_time, after
