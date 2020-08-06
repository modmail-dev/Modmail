import asyncio
import re
from datetime import datetime
from itertools import zip_longest
from typing import Optional, Union
from types import SimpleNamespace

import discord
from discord.ext import commands
from discord.utils import escape_markdown

from dateutil import parser
from natural.date import duration

from core import checks
from core.models import PermissionLevel, getLogger
from core.paginator import EmbedPaginatorSession
from core.thread import Thread
from core.time import UserFriendlyTime, human_timedelta
from core.utils import *

logger = getLogger(__name__)


class Modmail(commands.Cog):
    """Commands directly related to Modmail functionality."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @trigger_typing
    @checks.has_permissions(PermissionLevel.OWNER)
    async def setup(self, ctx):
        """
        Sets up a server for Modmail.

        You only need to run this command
        once after configuring Modmail.
        """

        if ctx.guild != self.bot.modmail_guild:
            return await ctx.send(
                f"You can only setup in the Modmail guild: {self.bot.modmail_guild}."
            )

        if self.bot.main_category is not None:
            logger.debug("Can't re-setup server, main_category is found.")
            return await ctx.send(f"{self.bot.modmail_guild} is already set up.")

        if self.bot.modmail_guild is None:
            embed = discord.Embed(
                title="Error",
                description="Modmail functioning guild not found.",
                color=self.bot.error_color,
            )
            return await ctx.send(embed=embed)

        overwrites = {
            self.bot.modmail_guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.bot.modmail_guild.me: discord.PermissionOverwrite(read_messages=True),
        }

        for level in PermissionLevel:
            if level <= PermissionLevel.REGULAR:
                continue
            permissions = self.bot.config["level_permissions"].get(level.name, [])
            for perm in permissions:
                perm = int(perm)
                if perm == -1:
                    key = self.bot.modmail_guild.default_role
                else:
                    key = self.bot.modmail_guild.get_member(perm)
                    if key is None:
                        key = self.bot.modmail_guild.get_role(perm)
                if key is not None:
                    logger.info("Granting %s access to Modmail category.", key.name)
                    overwrites[key] = discord.PermissionOverwrite(read_messages=True)

        category = await self.bot.modmail_guild.create_category(
            name="Modmail", overwrites=overwrites
        )

        await category.edit(position=0)

        log_channel = await self.bot.modmail_guild.create_text_channel(
            name="bot-logs", category=category
        )

        embed = discord.Embed(
            title="Friendly Reminder",
            description=f"You may use the `{self.bot.prefix}config set log_channel_id "
            "<channel-id>` command to set up a custom log channel, then you can delete this default "
            f"{log_channel.mention} log channel.",
            color=self.bot.main_color,
        )

        embed.add_field(
            name="Thanks for using our bot!",
            value="If you like what you see, consider giving the "
            "[repo a star](https://github.com/kyb3r/modmail) :star: and if you are "
            "feeling extra generous, buy us coffee on [Patreon](https://patreon.com/kyber) :heart:!",
        )

        embed.set_footer(text=f'Type "{self.bot.prefix}help" for a complete list of commands.')
        await log_channel.send(embed=embed)

        self.bot.config["main_category_id"] = category.id
        self.bot.config["log_channel_id"] = log_channel.id

        await self.bot.config.update()
        await ctx.send(
            "**Successfully set up server.**\n"
            "Consider setting permission levels to give access to roles "
            "or users the ability to use Modmail.\n\n"
            f"Type:\n- `{self.bot.prefix}permissions` and `{self.bot.prefix}permissions add` "
            "for more info on setting permissions.\n"
            f"- `{self.bot.prefix}config help` for a list of available customizations."
        )

        if not self.bot.config["command_permissions"] and not self.bot.config["level_permissions"]:
            await self.bot.update_perms(PermissionLevel.REGULAR, -1)
            for owner_id in self.bot.bot_owner_ids:
                await self.bot.update_perms(PermissionLevel.OWNER, owner_id)

    @commands.group(aliases=["snippets"], invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet(self, ctx, *, name: str.lower = None):
        """
        Create pre-defined messages for use in threads.

        When `{prefix}snippet` is used by itself, this will retrieve
        a list of snippets that are currently set. `{prefix}snippet-name` will show what the
        snippet point to.

        To create a snippet:
        - `{prefix}snippet add snippet-name A pre-defined text.`

        You can use your snippet in a thread channel
        with `{prefix}snippet-name`, the message "A pre-defined text."
        will be sent to the recipient.

        Currently, there is not a built-in anonymous snippet command; however, a workaround
        is available using `{prefix}alias`. Here is how:
        - `{prefix}alias add snippet-name anonreply A pre-defined anonymous text.`

        See also `{prefix}alias`.
        """

        if name is not None:
            val = self.bot.snippets.get(name)
            if val is None:
                embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
            else:
                embed = discord.Embed(
                    title=f'Snippet - "{name}":', description=val, color=self.bot.main_color
                )
            return await ctx.send(embed=embed)

        if not self.bot.snippets:
            embed = discord.Embed(
                color=self.bot.error_color, description="You dont have any snippets at the moment."
            )
            embed.set_footer(text=f'Check "{self.bot.prefix}help snippet add" to add a snippet.')
            embed.set_author(name="Snippets", icon_url=ctx.guild.icon_url)
            return await ctx.send(embed=embed)

        embeds = []

        for i, names in enumerate(zip_longest(*(iter(sorted(self.bot.snippets)),) * 15)):
            description = format_description(i, names)
            embed = discord.Embed(color=self.bot.main_color, description=description)
            embed.set_author(name="Snippets", icon_url=ctx.guild.icon_url)
            embeds.append(embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @snippet.command(name="raw")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_raw(self, ctx, *, name: str.lower):
        """
        View the raw content of a snippet.
        """
        val = self.bot.snippets.get(name)
        if val is None:
            embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
        else:
            val = truncate(escape_code_block(val), 2048 - 7)
            embed = discord.Embed(
                title=f'Raw snippet - "{name}":',
                description=f"```\n{val}```",
                color=self.bot.main_color,
            )

        return await ctx.send(embed=embed)

    @snippet.command(name="add")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_add(self, ctx, name: str.lower, *, value: commands.clean_content):
        """
        Add a snippet.

        Simply to add a snippet, do: ```
        {prefix}snippet add hey hello there :)
        ```
        then when you type `{prefix}hey`, "hello there :)" will get sent to the recipient.

        To add a multi-word snippet name, use quotes: ```
        {prefix}snippet add "two word" this is a two word snippet.
        ```
        """
        if name in self.bot.snippets:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"Snippet `{name}` already exists.",
            )
            return await ctx.send(embed=embed)

        if name in self.bot.aliases:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"An alias that shares the same name exists: `{name}`.",
            )
            return await ctx.send(embed=embed)

        if len(name) > 120:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description="Snippet names cannot be longer than 120 characters.",
            )
            return await ctx.send(embed=embed)

        self.bot.snippets[name] = value
        await self.bot.config.update()

        embed = discord.Embed(
            title="Added snippet",
            color=self.bot.main_color,
            description="Successfully created snippet.",
        )
        return await ctx.send(embed=embed)

    @snippet.command(name="remove", aliases=["del", "delete"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_remove(self, ctx, *, name: str.lower):
        """Remove a snippet."""

        if name in self.bot.snippets:
            embed = discord.Embed(
                title="Removed snippet",
                color=self.bot.main_color,
                description=f"Snippet `{name}` is now deleted.",
            )
            self.bot.snippets.pop(name)
            await self.bot.config.update()
        else:
            embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
        await ctx.send(embed=embed)

    @snippet.command(name="edit")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_edit(self, ctx, name: str.lower, *, value):
        """
        Edit a snippet.

        To edit a multi-word snippet name, use quotes: ```
        {prefix}snippet edit "two word" this is a new two word snippet.
        ```
        """
        if name in self.bot.snippets:
            self.bot.snippets[name] = value
            await self.bot.config.update()

            embed = discord.Embed(
                title="Edited snippet",
                color=self.bot.main_color,
                description=f'`{name}` will now send "{value}".',
            )
        else:
            embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
        await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @checks.thread_only()
    async def move(self, ctx, category: discord.CategoryChannel, *, specifics: str = None):
        """
        Move a thread to another category.

        `category` may be a category ID, mention, or name.
        `specifics` is a string which takes in arguments on how to perform the move. Ex: "silently"
        """
        thread = ctx.thread
        silent = False

        if specifics:
            silent_words = ["silent", "silently"]
            silent = any(word in silent_words for word in specifics.split())

        await thread.channel.edit(category=category, sync_permissions=True)

        if self.bot.config["thread_move_notify"] and not silent:
            embed = discord.Embed(
                title="Thread Moved",
                description=self.bot.config["thread_move_response"],
                color=self.bot.main_color,
            )
            await thread.recipient.send(embed=embed)

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    async def send_scheduled_close_message(self, ctx, after, silent=False):
        human_delta = human_timedelta(after.dt)

        silent = "*silently* " if silent else ""

        embed = discord.Embed(
            title="Scheduled close",
            description=f"This thread will close {silent}in {human_delta}.",
            color=self.bot.error_color,
        )

        if after.arg and not silent:
            embed.add_field(name="Message", value=after.arg)

        embed.set_footer(text="Closing will be cancelled if a thread message is sent.")
        embed.timestamp = after.dt

        await ctx.send(embed=embed)

    @commands.command(usage="[after] [close message]")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def close(self, ctx, *, after: UserFriendlyTime = None):
        """
        Close the current thread.

        Close after a period of time:
        - `{prefix}close in 5 hours`
        - `{prefix}close 2m30s`

        Custom close messages:
        - `{prefix}close 2 hours The issue has been resolved.`
        - `{prefix}close We will contact you once we find out more.`

        Silently close a thread (no message)
        - `{prefix}close silently`
        - `{prefix}close in 10m silently`

        Stop a thread from closing:
        - `{prefix}close cancel`
        """

        thread = ctx.thread

        now = datetime.utcnow()

        close_after = (after.dt - now).total_seconds() if after else 0
        message = after.arg if after else None
        silent = str(message).lower() in {"silent", "silently"}
        cancel = str(message).lower() == "cancel"

        if cancel:

            if thread.close_task is not None or thread.auto_close_task is not None:
                await thread.cancel_closure(all=True)
                embed = discord.Embed(
                    color=self.bot.error_color, description="Scheduled close has been cancelled."
                )
            else:
                embed = discord.Embed(
                    color=self.bot.error_color,
                    description="This thread has not already been scheduled to close.",
                )

            return await ctx.send(embed=embed)

        if after and after.dt > now:
            await self.send_scheduled_close_message(ctx, after, silent)

        await thread.close(closer=ctx.author, after=close_after, message=message, silent=silent)

    @staticmethod
    def parse_user_or_role(ctx, user_or_role):
        mention = None
        if user_or_role is None:
            mention = ctx.author.mention
        elif hasattr(user_or_role, "mention"):
            mention = user_or_role.mention
        elif user_or_role in {"here", "everyone", "@here", "@everyone"}:
            mention = "@" + user_or_role.lstrip("@")
        return mention

    @commands.command(aliases=["alert"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def notify(
        self, ctx, *, user_or_role: Union[discord.Role, User, str.lower, None] = None
    ):
        """
        Notify a user or role when the next thread message received.

        Once a thread message is received, `user_or_role` will be pinged once.

        Leave `user_or_role` empty to notify yourself.
        `@here` and `@everyone` can be substituted with `here` and `everyone`.
        `user_or_role` may be a user ID, mention, name. role ID, mention, name, "everyone", or "here".
        """
        mention = self.parse_user_or_role(ctx, user_or_role)
        if mention is None:
            raise commands.BadArgument(f"{user_or_role} is not a valid user or role.")

        thread = ctx.thread

        if str(thread.id) not in self.bot.config["notification_squad"]:
            self.bot.config["notification_squad"][str(thread.id)] = []

        mentions = self.bot.config["notification_squad"][str(thread.id)]

        if mention in mentions:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{mention} is already going to be mentioned.",
            )
        else:
            mentions.append(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=self.bot.main_color,
                description=f"{mention} will be mentioned on the next message received.",
            )
        return await ctx.send(embed=embed)

    @commands.command(aliases=["unalert"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def unnotify(
        self, ctx, *, user_or_role: Union[discord.Role, User, str.lower, None] = None
    ):
        """
        Un-notify a user, role, or yourself from a thread.

        Leave `user_or_role` empty to un-notify yourself.
        `@here` and `@everyone` can be substituted with `here` and `everyone`.
        `user_or_role` may be a user ID, mention, name, role ID, mention, name, "everyone", or "here".
        """
        mention = self.parse_user_or_role(ctx, user_or_role)
        if mention is None:
            mention = f"`{user_or_role}`"

        thread = ctx.thread

        if str(thread.id) not in self.bot.config["notification_squad"]:
            self.bot.config["notification_squad"][str(thread.id)] = []

        mentions = self.bot.config["notification_squad"][str(thread.id)]

        if mention not in mentions:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{mention} does not have a pending notification.",
            )
        else:
            mentions.remove(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=self.bot.main_color, description=f"{mention} will no longer be notified."
            )
        return await ctx.send(embed=embed)

    @commands.command(aliases=["sub"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def subscribe(
        self, ctx, *, user_or_role: Union[discord.Role, User, str.lower, None] = None
    ):
        """
        Notify a user, role, or yourself for every thread message received.

        You will be pinged for every thread message received until you unsubscribe.

        Leave `user_or_role` empty to subscribe yourself.
        `@here` and `@everyone` can be substituted with `here` and `everyone`.
        `user_or_role` may be a user ID, mention, name, role ID, mention, name, "everyone", or "here".
        """
        mention = self.parse_user_or_role(ctx, user_or_role)
        if mention is None:
            raise commands.BadArgument(f"{user_or_role} is not a valid user or role.")

        thread = ctx.thread

        if str(thread.id) not in self.bot.config["subscriptions"]:
            self.bot.config["subscriptions"][str(thread.id)] = []

        mentions = self.bot.config["subscriptions"][str(thread.id)]

        if mention in mentions:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{mention} is not subscribed to this thread.",
            )
        else:
            mentions.append(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=self.bot.main_color,
                description=f"{mention} will now be notified of all messages received.",
            )
        return await ctx.send(embed=embed)

    @commands.command(aliases=["unsub"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def unsubscribe(
        self, ctx, *, user_or_role: Union[discord.Role, User, str.lower, None] = None
    ):
        """
        Unsubscribe a user, role, or yourself from a thread.

        Leave `user_or_role` empty to unsubscribe yourself.
        `@here` and `@everyone` can be substituted with `here` and `everyone`.
        `user_or_role` may be a user ID, mention, name, role ID, mention, name, "everyone", or "here".
        """
        mention = self.parse_user_or_role(ctx, user_or_role)
        if mention is None:
            mention = f"`{user_or_role}`"

        thread = ctx.thread

        if str(thread.id) not in self.bot.config["subscriptions"]:
            self.bot.config["subscriptions"][str(thread.id)] = []

        mentions = self.bot.config["subscriptions"][str(thread.id)]

        if mention not in mentions:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{mention} is not subscribed to this thread.",
            )
        else:
            mentions.remove(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=self.bot.main_color,
                description=f"{mention} is now unsubscribed from this thread.",
            )
        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def nsfw(self, ctx):
        """Flags a Modmail thread as NSFW (not safe for work)."""
        await ctx.channel.edit(nsfw=True)
        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def sfw(self, ctx):
        """Flags a Modmail thread as SFW (safe for work)."""
        await ctx.channel.edit(nsfw=False)
        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def loglink(self, ctx):
        """Retrieves the link to the current thread's logs."""
        log_link = await self.bot.api.get_log_link(ctx.channel.id)
        await ctx.send(embed=discord.Embed(color=self.bot.main_color, description=log_link))

    def format_log_embeds(self, logs, avatar_url):
        embeds = []
        logs = tuple(logs)
        title = f"Total Results Found ({len(logs)})"

        for entry in logs:
            created_at = parser.parse(entry["created_at"])

            prefix = self.bot.config["log_url_prefix"].strip("/")
            if prefix == "NONE":
                prefix = ""
            log_url = f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{entry['key']}"

            username = entry["recipient"]["name"] + "#"
            username += entry["recipient"]["discriminator"]

            embed = discord.Embed(color=self.bot.main_color, timestamp=created_at)
            embed.set_author(name=f"{title} - {username}", icon_url=avatar_url, url=log_url)
            embed.url = log_url
            embed.add_field(name="Created", value=duration(created_at, now=datetime.utcnow()))
            closer = entry.get("closer")
            if closer is None:
                closer_msg = "Unknown"
            else:
                closer_msg = f"<@{closer['id']}>"
            embed.add_field(name="Closed By", value=closer_msg)

            if entry["recipient"]["id"] != entry["creator"]["id"]:
                embed.add_field(name="Created by", value=f"<@{entry['creator']['id']}>")

            embed.add_field(name="Preview", value=format_preview(entry["messages"]), inline=False)

            if closer is not None:
                # BUG: Currently, logviewer can't display logs without a closer.
                embed.add_field(name="Link", value=log_url)
            else:
                logger.debug("Invalid log entry: no closer.")
                embed.add_field(name="Log Key", value=f"`{entry['key']}`")

            embed.set_footer(text="Recipient ID: " + str(entry["recipient"]["id"]))
            embeds.append(embed)
        return embeds

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def logs(self, ctx, *, user: User = None):
        """
        Get previous Modmail thread logs of a member.

        Leave `user` blank when this command is used within a
        thread channel to show logs for the current recipient.
        `user` may be a user ID, mention, or name.
        """

        await ctx.trigger_typing()

        if not user:
            thread = ctx.thread
            if not thread:
                raise commands.MissingRequiredArgument(SimpleNamespace(name="member"))
            user = thread.recipient

        default_avatar = "https://cdn.discordapp.com/embed/avatars/0.png"
        icon_url = getattr(user, "avatar_url", default_avatar)

        logs = await self.bot.api.get_user_logs(user.id)

        if not any(not log["open"] for log in logs):
            embed = discord.Embed(
                color=self.bot.error_color,
                description="This user does not have any previous logs.",
            )
            return await ctx.send(embed=embed)

        logs = reversed([log for log in logs if not log["open"]])

        embeds = self.format_log_embeds(logs, avatar_url=icon_url)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @logs.command(name="closed-by", aliases=["closeby"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def logs_closed_by(self, ctx, *, user: User = None):
        """
        Get all logs closed by the specified user.

        If no `user` is provided, the user will be the person who sent this command.
        `user` may be a user ID, mention, or name.
        """
        user = user if user is not None else ctx.author

        entries = await self.bot.api.search_closed_by(user.id)
        embeds = self.format_log_embeds(entries, avatar_url=self.bot.guild.icon_url)

        if not embeds:
            embed = discord.Embed(
                color=self.bot.error_color,
                description="No log entries have been found for that query.",
            )
            return await ctx.send(embed=embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @logs.command(name="delete", aliases=["wipe"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def logs_delete(self, ctx, key_or_link: str):
        """
        Wipe a log entry from the database.
        """
        key = key_or_link.split("/")[-1]

        success = await self.bot.api.delete_log_entry(key)

        if not success:
            embed = discord.Embed(
                title="Error",
                description=f"Log entry `{key}` not found.",
                color=self.bot.error_color,
            )
        else:
            embed = discord.Embed(
                title="Success",
                description=f"Log entry `{key}` successfully deleted.",
                color=self.bot.main_color,
            )

        await ctx.send(embed=embed)

    @logs.command(name="responded")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def logs_responded(self, ctx, *, user: User = None):
        """
        Get all logs where the specified user has responded at least once.

        If no `user` is provided, the user will be the person who sent this command.
        `user` may be a user ID, mention, or name.
        """
        user = user if user is not None else ctx.author

        entries = await self.bot.api.get_responded_logs(user.id)

        embeds = self.format_log_embeds(entries, avatar_url=self.bot.guild.icon_url)

        if not embeds:
            embed = discord.Embed(
                color=self.bot.error_color,
                description=f"{getattr(user, 'mention', user.id)} has not responded to any threads.",
            )
            return await ctx.send(embed=embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @logs.command(name="search", aliases=["find"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def logs_search(self, ctx, limit: Optional[int] = None, *, query):
        """
        Retrieve all logs that contain messages with your query.

        Provide a `limit` to specify the maximum number of logs the bot should find.
        """

        await ctx.trigger_typing()

        entries = await self.bot.api.search_by_text(query, limit)

        embeds = self.format_log_embeds(entries, avatar_url=self.bot.guild.icon_url)

        if not embeds:
            embed = discord.Embed(
                color=self.bot.error_color,
                description="No log entries have been found for that query.",
            )
            return await ctx.send(embed=embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def reply(self, ctx, *, msg: str = ""):
        """
        Reply to a Modmail thread.

        Supports attachments and images as well as
        automatically embedding image URLs.
        """
        ctx.message.content = msg
        async with ctx.typing():
            await ctx.thread.reply(ctx.message)

    @commands.command(aliases=["formatreply"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def freply(self, ctx, *, msg: str = ""):
        """
        Reply to a Modmail thread with variables.

        Works just like `{prefix}reply`, however with the addition of three variables:
          - `{{channel}}` - the `discord.TextChannel` object
          - `{{recipient}}` - the `discord.User` object of the recipient
          - `{{author}}` - the `discord.User` object of the author

        Supports attachments and images as well as
        automatically embedding image URLs.
        """
        msg = self.bot.formatter.format(
            msg, channel=ctx.channel, recipient=ctx.thread.recipient, author=ctx.message.author
        )
        ctx.message.content = msg
        async with ctx.typing():
            await ctx.thread.reply(ctx.message)

    @commands.command(aliases=["anonreply", "anonymousreply"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def areply(self, ctx, *, msg: str = ""):
        """
        Reply to a thread anonymously.

        You can edit the anonymous user's name,
        avatar and tag using the config command.

        Edit the `anon_username`, `anon_avatar_url`
        and `anon_tag` config variables to do so.
        """
        ctx.message.content = msg
        async with ctx.typing():
            await ctx.thread.reply(ctx.message, anonymous=True)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def note(self, ctx, *, msg: str = ""):
        """
        Take a note about the current thread.

        Useful for noting context.
        """
        ctx.message.content = msg
        async with ctx.typing():
            msg = await ctx.thread.note(ctx.message)
            await msg.pin()

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def edit(self, ctx, message_id: Optional[int] = None, *, message: str):
        """
        Edit a message that was sent using the reply or anonreply command.

        If no `message_id` is provided,
        the last message sent by a staff will be edited.

        Note: attachments **cannot** be edited.
        """
        thread = ctx.thread

        try:
            await thread.edit_message(message_id, message)
        except ValueError:
            return await ctx.send(
                embed=discord.Embed(
                    title="Failed",
                    description="Cannot find a message to edit.",
                    color=self.bot.error_color,
                )
            )

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def contact(
        self,
        ctx,
        user: Union[discord.Member, discord.User],
        *,
        category: discord.CategoryChannel = None,
    ):
        """
        Create a thread with a specified member.

        If `category` is specified, the thread
        will be created in that specified category.

        `category`, if specified, may be a category ID, mention, or name.
        `user` may be a user ID, mention, or name.
        """

        if user.bot:
            embed = discord.Embed(
                color=self.bot.error_color, description="Cannot start a thread with a bot."
            )
            return await ctx.send(embed=embed)

        exists = await self.bot.threads.find(recipient=user)
        if exists:
            embed = discord.Embed(
                color=self.bot.error_color,
                description="A thread for this user already "
                f"exists in {exists.channel.mention}.",
            )
            await ctx.channel.send(embed=embed)

        else:
            thread = await self.bot.threads.create(user, creator=ctx.author, category=category)
            if self.bot.config["dm_disabled"] >= 1:
                logger.info("Contacting user %s when Modmail DM is disabled.", user)

            embed = discord.Embed(
                title="Created Thread",
                description=f"Thread started by {ctx.author.mention} for {user.mention}.",
                color=self.bot.main_color,
            )
            await thread.wait_until_ready()
            await thread.channel.send(embed=embed)
            sent_emoji, _ = await self.bot.retrieve_emoji()
            await self.bot.add_reaction(ctx.message, sent_emoji)
            await asyncio.sleep(3)
            await ctx.message.delete()

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def blocked(self, ctx):
        """Retrieve a list of blocked users."""

        embeds = [discord.Embed(title="Blocked Users", color=self.bot.main_color, description="")]

        users = []

        for id_, reason in self.bot.blocked_users.items():
            user = self.bot.get_user(int(id_))
            if user:
                users.append((user.mention, reason))
            else:
                try:
                    user = await self.bot.fetch_user(id_)
                    users.append((user.mention, reason))
                except discord.NotFound:
                    users.append((id_, reason))

        if users:
            embed = embeds[0]

            for mention, reason in users:
                line = mention + f" - {reason or 'No Reason Provided'}\n"
                if len(embed.description) + len(line) > 2048:
                    embed = discord.Embed(
                        title="Blocked Users (Continued)",
                        color=self.bot.main_color,
                        description=line,
                    )
                    embeds.append(embed)
                else:
                    embed.description += line
        else:
            embeds[0].description = "Currently there are no blocked users."

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @blocked.command(name="whitelist")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def blocked_whitelist(self, ctx, *, user: User = None):
        """
        Whitelist or un-whitelist a user from getting blocked.

        Useful for preventing users from getting blocked by account_age/guild_age restrictions.
        """
        if user is None:
            thread = ctx.thread
            if thread:
                user = thread.recipient
            else:
                return await ctx.send_help(ctx.command)

        mention = getattr(user, "mention", f"`{user.id}`")
        msg = ""

        if str(user.id) in self.bot.blocked_whitelisted_users:
            embed = discord.Embed(
                title="Success",
                description=f"{mention} is no longer whitelisted.",
                color=self.bot.main_color,
            )
            self.bot.blocked_whitelisted_users.remove(str(user.id))
            return await ctx.send(embed=embed)

        self.bot.blocked_whitelisted_users.append(str(user.id))

        if str(user.id) in self.bot.blocked_users:
            msg = self.bot.blocked_users.get(str(user.id)) or ""
            self.bot.blocked_users.pop(str(user.id))

        await self.bot.config.update()

        if msg.startswith("System Message: "):
            # If the user is blocked internally (for example: below minimum account age)
            # Show an extended message stating the original internal message
            reason = msg[16:].strip().rstrip(".")
            embed = discord.Embed(
                title="Success",
                description=f"{mention} was previously blocked internally for "
                f'"{reason}". {mention} is now whitelisted.',
                color=self.bot.main_color,
            )
        else:
            embed = discord.Embed(
                title="Success",
                color=self.bot.main_color,
                description=f"{mention} is now whitelisted.",
            )

        return await ctx.send(embed=embed)

    @commands.command(usage="[user] [duration] [reason]")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def block(self, ctx, user: Optional[User] = None, *, after: UserFriendlyTime = None):
        """
        Block a user from using Modmail.

        You may choose to set a time as to when the user will automatically be unblocked.

        Leave `user` blank when this command is used within a
        thread channel to block the current recipient.
        `user` may be a user ID, mention, or name.
        `duration` may be a simple "human-readable" time text. See `{prefix}help close` for examples.
        """

        if user is None:
            thread = ctx.thread
            if thread:
                user = thread.recipient
            elif after is None:
                raise commands.MissingRequiredArgument(SimpleNamespace(name="user"))
            else:
                raise commands.BadArgument(f'User "{after.arg}" not found.')

        mention = getattr(user, "mention", f"`{user.id}`")

        if str(user.id) in self.bot.blocked_whitelisted_users:
            embed = discord.Embed(
                title="Error",
                description=f"Cannot block {mention}, user is whitelisted.",
                color=self.bot.error_color,
            )
            return await ctx.send(embed=embed)

        reason = f"by {escape_markdown(ctx.author.name)}#{ctx.author.discriminator}"

        if after is not None:
            if "%" in reason:
                raise commands.BadArgument('The reason contains illegal character "%".')
            if after.arg:
                reason += f" for `{after.arg}`"
            if after.dt > after.now:
                reason += f" until {after.dt.isoformat()}"

        reason += "."

        msg = self.bot.blocked_users.get(str(user.id))
        if msg is None:
            msg = ""

        if str(user.id) in self.bot.blocked_users and msg:
            old_reason = msg.strip().rstrip(".")
            embed = discord.Embed(
                title="Success",
                description=f"{mention} was previously blocked {old_reason}.\n"
                f"{mention} is now blocked {reason}",
                color=self.bot.main_color,
            )
        else:
            embed = discord.Embed(
                title="Success",
                color=self.bot.main_color,
                description=f"{mention} is now blocked {reason}",
            )
        self.bot.blocked_users[str(user.id)] = reason
        await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def unblock(self, ctx, *, user: User = None):
        """
        Unblock a user from using Modmail.

        Leave `user` blank when this command is used within a
        thread channel to unblock the current recipient.
        `user` may be a user ID, mention, or name.
        """

        if user is None:
            thread = ctx.thread
            if thread:
                user = thread.recipient
            else:
                raise commands.MissingRequiredArgument(SimpleNamespace(name="user"))

        mention = getattr(user, "mention", f"`{user.id}`")
        name = getattr(user, "name", f"`{user.id}`")

        if str(user.id) in self.bot.blocked_users:
            msg = self.bot.blocked_users.pop(str(user.id)) or ""
            await self.bot.config.update()

            if msg.startswith("System Message: "):
                # If the user is blocked internally (for example: below minimum account age)
                # Show an extended message stating the original internal message
                reason = msg[16:].strip().rstrip(".") or "no reason"
                embed = discord.Embed(
                    title="Success",
                    description=f"{mention} was previously blocked internally {reason}.\n"
                    f"{mention} is no longer blocked.",
                    color=self.bot.main_color,
                )
                embed.set_footer(
                    text="However, if the original system block reason still applies, "
                    f"{name} will be automatically blocked again. "
                    f'Use "{self.bot.prefix}blocked whitelist {user.id}" to whitelist the user.'
                )
            else:
                embed = discord.Embed(
                    title="Success",
                    color=self.bot.main_color,
                    description=f"{mention} is no longer blocked.",
                )
        else:
            embed = discord.Embed(
                title="Error", description=f"{mention} is not blocked.", color=self.bot.error_color
            )

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def delete(self, ctx, message_id: int = None):
        """
        Delete a message that was sent using the reply command or a note.

        Deletes the previous message, unless a message ID is provided,
        which in that case, deletes the message with that message ID.

        Notes can only be deleted when a note ID is provided.
        """
        thread = ctx.thread

        try:
            await thread.delete_message(message_id, note=True)
        except ValueError as e:
            logger.warning("Failed to delete message: %s.", e)
            return await ctx.send(
                embed=discord.Embed(
                    title="Failed",
                    description="Cannot find a message to delete.",
                    color=self.bot.error_color,
                )
            )

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def repair(self, ctx):
        """
        Repair a thread broken by Discord.
        """
        sent_emoji, blocked_emoji = await self.bot.retrieve_emoji()

        if ctx.thread:
            user_id = match_user_id(ctx.channel.topic)
            if user_id == -1:
                logger.info("Setting current channel's topic to User ID.")
                await ctx.channel.edit(topic=f"User ID: {ctx.thread.id}")
            return await self.bot.add_reaction(ctx.message, sent_emoji)

        logger.info("Attempting to fix a broken thread %s.", ctx.channel.name)

        # Search cache for channel
        user_id, thread = next(
            ((k, v) for k, v in self.bot.threads.cache.items() if v.channel == ctx.channel),
            (-1, None),
        )
        if thread is not None:
            logger.debug("Found thread with tempered ID.")
            await ctx.channel.edit(reason="Fix broken Modmail thread", topic=f"User ID: {user_id}")
            return await self.bot.add_reaction(ctx.message, sent_emoji)

        # find genesis message to retrieve User ID
        async for message in ctx.channel.history(limit=10, oldest_first=True):
            if (
                message.author == self.bot.user
                and message.embeds
                and message.embeds[0].color
                and message.embeds[0].color.value == self.bot.main_color
                and message.embeds[0].footer.text
            ):
                user_id = match_user_id(message.embeds[0].footer.text)
                if user_id != -1:
                    recipient = self.bot.get_user(user_id)
                    if recipient is None:
                        self.bot.threads.cache[user_id] = thread = Thread(
                            self.bot.threads, user_id, ctx.channel
                        )
                    else:
                        self.bot.threads.cache[user_id] = thread = Thread(
                            self.bot.threads, recipient, ctx.channel
                        )
                    thread.ready = True
                    logger.info(
                        "Setting current channel's topic to User ID and created new thread."
                    )
                    await ctx.channel.edit(
                        reason="Fix broken Modmail thread", topic=f"User ID: {user_id}"
                    )
                    return await self.bot.add_reaction(ctx.message, sent_emoji)

        else:
            logger.warning("No genesis message found.")

        # match username from channel name
        # username-1234, username-1234_1, username-1234_2
        m = re.match(r"^(.+)-(\d{4})(?:_\d+)?$", ctx.channel.name)
        if m is not None:
            users = set(
                filter(
                    lambda member: member.name == m.group(1)
                    and member.discriminator == m.group(2),
                    ctx.guild.members,
                )
            )
            if len(users) == 1:
                user = users.pop()
                name = format_channel_name(
                    user, self.bot.modmail_guild, exclude_channel=ctx.channel
                )
                recipient = self.bot.get_user(user.id)
                if user.id in self.bot.threads.cache:
                    thread = self.bot.threads.cache[user.id]
                    if thread.channel:
                        embed = discord.Embed(
                            title="Delete Channel",
                            description="This thread channel is no longer in use. "
                            f"All messages will be directed to {ctx.channel.mention} instead.",
                            color=self.bot.error_color,
                        )
                        embed.set_footer(
                            text='Please manually delete this channel, do not use "{prefix}close".'
                        )
                        try:
                            await thread.channel.send(embed=embed)
                        except discord.HTTPException:
                            pass
                if recipient is None:
                    self.bot.threads.cache[user.id] = thread = Thread(
                        self.bot.threads, user_id, ctx.channel
                    )
                else:
                    self.bot.threads.cache[user.id] = thread = Thread(
                        self.bot.threads, recipient, ctx.channel
                    )
                thread.ready = True
                logger.info("Setting current channel's topic to User ID and created new thread.")
                await ctx.channel.edit(
                    reason="Fix broken Modmail thread", name=name, topic=f"User ID: {user.id}"
                )
                return await self.bot.add_reaction(ctx.message, sent_emoji)

            elif len(users) >= 2:
                logger.info("Multiple users with the same name and discriminator.")
        return await self.bot.add_reaction(ctx.message, blocked_emoji)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def enable(self, ctx):
        """
        Re-enables DM functionalities of Modmail.

        Undo's the `{prefix}disable` command, all DM will be relayed after running this command.
        """
        embed = discord.Embed(
            title="Success",
            description="Modmail will now accept all DM messages.",
            color=self.bot.main_color,
        )

        if self.bot.config["dm_disabled"] != 0:
            self.bot.config["dm_disabled"] = 0
            await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def disable(self, ctx):
        """
        Disable partial or full Modmail thread functions.

        To stop all new threads from being created, do `{prefix}disable new`.
        To stop all existing threads from DMing Modmail, do `{prefix}disable all`.
        To check if the DM function for Modmail is enabled, do `{prefix}isenable`.
        """
        await ctx.send_help(ctx.command)

    @disable.command(name="new")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def disable_new(self, ctx):
        """
        Stop accepting new Modmail threads.

        No new threads can be created through DM.
        """
        embed = discord.Embed(
            title="Success",
            description="Modmail will not create any new threads.",
            color=self.bot.main_color,
        )
        if self.bot.config["dm_disabled"] < 1:
            self.bot.config["dm_disabled"] = 1
            await self.bot.config.update()

        return await ctx.send(embed=embed)

    @disable.command(name="all")
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def disable_all(self, ctx):
        """
        Disables all DM functionalities of Modmail.

        No new threads can be created through DM nor no further DM messages will be relayed.
        """
        embed = discord.Embed(
            title="Success",
            description="Modmail will not accept any DM messages.",
            color=self.bot.main_color,
        )

        if self.bot.config["dm_disabled"] != 2:
            self.bot.config["dm_disabled"] = 2
            await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def isenable(self, ctx):
        """
        Check if the DM functionalities of Modmail is enabled.
        """

        if self.bot.config["dm_disabled"] == 1:
            embed = discord.Embed(
                title="New Threads Disabled",
                description="Modmail is not creating new threads.",
                color=self.bot.error_color,
            )
        elif self.bot.config["dm_disabled"] == 2:
            embed = discord.Embed(
                title="All DM Disabled",
                description="Modmail is not accepting any DM messages for new and existing threads.",
                color=self.bot.error_color,
            )
        else:
            embed = discord.Embed(
                title="Enabled",
                description="Modmail now is accepting all DM messages.",
                color=self.bot.main_color,
            )

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Modmail(bot))
