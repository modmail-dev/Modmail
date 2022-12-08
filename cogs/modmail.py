import asyncio
import re
from datetime import datetime, timezone
from itertools import zip_longest
from typing import Optional, Union, List, Tuple, Literal
from types import SimpleNamespace

import discord
from discord.ext import commands
from discord.ext.commands.view import StringView
from discord.ext.commands.cooldowns import BucketType
from discord.role import Role
from discord.utils import escape_markdown

from dateutil import parser

from core import checks
from core.models import DMDisabled, PermissionLevel, SimilarCategoryConverter, getLogger
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
            return await ctx.send(f"You can only setup in the Modmail guild: {self.bot.modmail_guild}.")

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

        category = await self.bot.modmail_guild.create_category(name="Modmail", overwrites=overwrites)

        await category.edit(position=0)

        log_channel = await self.bot.modmail_guild.create_text_channel(name="bot-logs", category=category)

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
            snippet_name = self.bot._resolve_snippet(name)

            if snippet_name is None:
                embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
            else:
                val = self.bot.snippets[snippet_name]
                embed = discord.Embed(
                    title=f'Snippet - "{snippet_name}":', description=val, color=self.bot.main_color
                )
            return await ctx.send(embed=embed)

        if not self.bot.snippets:
            embed = discord.Embed(
                color=self.bot.error_color, description="You dont have any snippets at the moment."
            )
            embed.set_footer(text=f'Check "{self.bot.prefix}help snippet add" to add a snippet.')
            embed.set_author(name="Snippets", icon_url=self.bot.get_guild_icon(guild=ctx.guild))
            return await ctx.send(embed=embed)

        embeds = []

        for i, names in enumerate(zip_longest(*(iter(sorted(self.bot.snippets)),) * 15)):
            description = format_description(i, names)
            embed = discord.Embed(color=self.bot.main_color, description=description)
            embed.set_author(name="Snippets", icon_url=self.bot.get_guild_icon(guild=ctx.guild))
            embeds.append(embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @snippet.command(name="raw")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_raw(self, ctx, *, name: str.lower):
        """
        View the raw content of a snippet.
        """
        snippet_name = self.bot._resolve_snippet(name)
        if snippet_name is None:
            embed = create_not_found_embed(name, self.bot.snippets.keys(), "Snippet")
        else:
            val = truncate(escape_code_block(self.bot.snippets[snippet_name]), 2048 - 7)
            embed = discord.Embed(
                title=f'Raw snippet - "{snippet_name}":',
                description=f"```\n{val}```",
                color=self.bot.main_color,
            )

        return await ctx.send(embed=embed)

    @snippet.command(name="add", aliases=["create", "make"])
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
        if self.bot.get_command(name):
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"A command with the same name already exists: `{name}`.",
            )
            return await ctx.send(embed=embed)
        elif name in self.bot.snippets:
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

    def _fix_aliases(self, snippet_being_deleted: str) -> Tuple[List[str]]:
        """
        Remove references to the snippet being deleted from aliases.

        Direct aliases to snippets are deleted, and aliases having
        other steps are edited.

        A tuple of dictionaries are returned. The first dictionary
        contains a mapping of alias names which were deleted to their
        original value, and the second dictionary contains a mapping
        of alias names which were edited to their original value.
        """
        deleted = {}
        edited = {}

        # Using a copy since we might need to delete aliases
        for alias, val in self.bot.aliases.copy().items():
            values = parse_alias(val)

            save_aliases = []

            for val in values:
                view = StringView(val)
                linked_command = view.get_word().lower()
                message = view.read_rest()

                if linked_command == snippet_being_deleted:
                    continue

                is_valid_snippet = snippet_being_deleted in self.bot.snippets

                if not self.bot.get_command(linked_command) and not is_valid_snippet:
                    alias_command = self.bot.aliases[linked_command]
                    save_aliases.extend(normalize_alias(alias_command, message))
                else:
                    save_aliases.append(val)

            if not save_aliases:
                original_value = self.bot.aliases.pop(alias)
                deleted[alias] = original_value
            else:
                original_alias = self.bot.aliases[alias]
                new_alias = " && ".join(f'"{a}"' for a in save_aliases)

                if original_alias != new_alias:
                    self.bot.aliases[alias] = new_alias
                    edited[alias] = original_alias

        return deleted, edited

    @snippet.command(name="remove", aliases=["del", "delete"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def snippet_remove(self, ctx, *, name: str.lower):
        """Remove a snippet."""
        if name in self.bot.snippets:
            deleted_aliases, edited_aliases = self._fix_aliases(name)

            deleted_aliases_string = ",".join(f"`{alias}`" for alias in deleted_aliases)
            if len(deleted_aliases) == 1:
                deleted_aliases_output = f"The `{deleted_aliases_string}` direct alias has been removed."
            elif deleted_aliases:
                deleted_aliases_output = (
                    f"The following direct aliases have been removed: {deleted_aliases_string}."
                )
            else:
                deleted_aliases_output = None

            if len(edited_aliases) == 1:
                alias, val = edited_aliases.popitem()
                edited_aliases_output = (
                    f"Steps pointing to this snippet have been removed from the `{alias}` alias"
                    f" (previous value: `{val}`).`"
                )
            elif edited_aliases:
                alias_list = "\n".join(
                    [
                        f"- `{alias_name}` (previous value: `{val}`)"
                        for alias_name, val in edited_aliases.items()
                    ]
                )
                edited_aliases_output = (
                    f"Steps pointing to this snippet have been removed from the following aliases:"
                    f"\n\n{alias_list}"
                )
            else:
                edited_aliases_output = None

            description = f"Snippet `{name}` is now deleted."
            if deleted_aliases_output:
                description += f"\n\n{deleted_aliases_output}"
            if edited_aliases_output:
                description += f"\n\n{edited_aliases_output}"

            embed = discord.Embed(
                title="Removed snippet",
                color=self.bot.main_color,
                description=description,
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

    @commands.command(usage="<category> [options]")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @checks.thread_only()
    async def move(self, ctx, *, arguments):
        """
        Move a thread to another category.

        `category` may be a category ID, mention, or name.
        `options` is a string which takes in arguments on how to perform the move. Ex: "silently"
        """
        split_args = arguments.strip('"').split(" ")
        category = None

        # manually parse arguments, consumes as much of args as possible for category
        for i in range(len(split_args)):
            try:
                if i == 0:
                    fmt = arguments
                else:
                    fmt = " ".join(split_args[:-i])

                category = await SimilarCategoryConverter().convert(ctx, fmt)
            except commands.BadArgument:
                if i == len(split_args) - 1:
                    # last one
                    raise
                pass
            else:
                break

        if not category:
            raise commands.ChannelNotFound(arguments)

        options = " ".join(arguments.split(" ")[-i:])

        thread = ctx.thread
        silent = False

        if options:
            silent_words = ["silent", "silently"]
            silent = any(word in silent_words for word in options.split())

        await thread.channel.move(
            category=category, end=True, sync_permissions=True, reason=f"{ctx.author} moved this thread."
        )

        if self.bot.config["thread_move_notify"] and not silent:
            embed = discord.Embed(
                title=self.bot.config["thread_move_title"],
                description=self.bot.config["thread_move_response"],
                color=self.bot.main_color,
            )
            await thread.recipient.send(embed=embed)

        if self.bot.config["thread_move_notify_mods"]:
            mention = self.bot.config["mention"]
            if mention is not None:
                msg = f"{mention}, thread has been moved."
            else:
                msg = "Thread has been moved."
            await thread.channel.send(msg)

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    async def send_scheduled_close_message(self, ctx, after, silent=False):
        human_delta = human_timedelta(after.dt)

        silent = "*silently* " if silent else ""

        embed = discord.Embed(
            title="Scheduled close",
            description=f"This thread will close {silent}{human_delta}.",
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
    async def close(
        self,
        ctx,
        option: Optional[Literal["silent", "silently", "cancel"]] = "",
        *,
        after: UserFriendlyTime = None,
    ):
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

        close_after = (after.dt - after.now).total_seconds() if after else 0
        silent = any(x == option for x in {"silent", "silently"})
        cancel = option == "cancel"

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

        message = after.arg if after else None
        if self.bot.config["require_close_reason"] and message is None:
            raise commands.BadArgument("Provide a reason for closing the thread.")

        if after and after.dt > after.now:
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
    async def notify(self, ctx, *, user_or_role: Union[discord.Role, User, str.lower, None] = None):
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
    async def unnotify(self, ctx, *, user_or_role: Union[discord.Role, User, str.lower, None] = None):
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
    async def subscribe(self, ctx, *, user_or_role: Union[discord.Role, User, str.lower, None] = None):
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
                description=f"{mention} is already subscribed to this thread.",
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
    async def unsubscribe(self, ctx, *, user_or_role: Union[discord.Role, User, str.lower, None] = None):
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
    async def msglink(self, ctx, message_id: int):
        """Retrieves the link to a message in the current thread."""
        try:
            message = await ctx.thread.recipient.fetch_message(message_id)
        except discord.NotFound:
            embed = discord.Embed(
                color=self.bot.error_color, description="Message not found or no longer exists."
            )
        else:
            embed = discord.Embed(color=self.bot.main_color, description=message.jump_url)
        await ctx.send(embed=embed)

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
            created_at = parser.parse(entry["created_at"]).astimezone(timezone.utc)

            prefix = self.bot.config["log_url_prefix"].strip("/")
            if prefix == "NONE":
                prefix = ""
            log_url = (
                f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{entry['key']}"
            )

            username = entry["recipient"]["name"] + "#"
            username += entry["recipient"]["discriminator"]

            embed = discord.Embed(color=self.bot.main_color, timestamp=created_at)
            embed.set_author(name=f"{title} - {username}", icon_url=avatar_url, url=log_url)
            embed.url = log_url
            embed.add_field(name="Created", value=human_timedelta(created_at))
            closer = entry.get("closer")
            if closer is None:
                closer_msg = "Unknown"
            else:
                closer_msg = f"<@{closer['id']}>"
            embed.add_field(name="Closed By", value=closer_msg)

            if entry["recipient"]["id"] != entry["creator"]["id"]:
                embed.add_field(name="Created by", value=f"<@{entry['creator']['id']}>")

            if entry.get("title"):
                embed.add_field(name="Title", value=entry["title"], inline=False)

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

    @commands.command(cooldown_after_parsing=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    @commands.cooldown(1, 600, BucketType.channel)
    async def title(self, ctx, *, name: str):
        """Sets title for a thread"""
        await ctx.thread.set_title(name)
        sent_emoji, _ = await self.bot.retrieve_emoji()
        await ctx.message.pin()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command(usage="<users_or_roles...> [options]", cooldown_after_parsing=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    @commands.cooldown(1, 600, BucketType.channel)
    async def adduser(self, ctx, *users_arg: Union[discord.Member, discord.Role, str]):
        """Adds a user to a modmail thread

        `options` can be `silent` or `silently`.
        """
        silent = False
        users = []
        for u in users_arg:
            if isinstance(u, str):
                if "silent" in u or "silently" in u:
                    silent = True
            elif isinstance(u, discord.Role):
                users += u.members
            elif isinstance(u, discord.Member):
                users.append(u)

        for u in users:
            # u is a discord.Member
            curr_thread = await self.bot.threads.find(recipient=u)
            if curr_thread == ctx.thread:
                users.remove(u)
                continue

            if curr_thread:
                em = discord.Embed(
                    title="Error",
                    description=f"{u.mention} is already in a thread: {curr_thread.channel.mention}.",
                    color=self.bot.error_color,
                )
                await ctx.send(embed=em)
                ctx.command.reset_cooldown(ctx)
                return

        if not users:
            em = discord.Embed(
                title="Error",
                description="All users are already in the thread.",
                color=self.bot.error_color,
            )
            await ctx.send(embed=em)
            ctx.command.reset_cooldown(ctx)
            return

        if len(users + ctx.thread.recipients) > 5:
            em = discord.Embed(
                title="Error",
                description="Only 5 users are allowed in a group conversation",
                color=self.bot.error_color,
            )
            await ctx.send(embed=em)
            ctx.command.reset_cooldown(ctx)
            return

        to_exec = []
        if not silent:
            description = self.bot.formatter.format(
                self.bot.config["private_added_to_group_response"], moderator=ctx.author
            )
            em = discord.Embed(
                title=self.bot.config["private_added_to_group_title"],
                description=description,
                color=self.bot.main_color,
            )
            if self.bot.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()
            em.set_footer(text=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            for u in users:
                to_exec.append(u.send(embed=em))

            description = self.bot.formatter.format(
                self.bot.config["public_added_to_group_response"],
                moderator=ctx.author,
                users=", ".join(u.name for u in users),
            )
            em = discord.Embed(
                title=self.bot.config["public_added_to_group_title"],
                description=description,
                color=self.bot.main_color,
            )
            if self.bot.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()
            em.set_footer(text=f"{users[0]}", icon_url=users[0].display_avatar.url)

            for i in ctx.thread.recipients:
                if i not in users:
                    to_exec.append(i.send(embed=em))

        await ctx.thread.add_users(users)
        if to_exec:
            await asyncio.gather(*to_exec)

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command(usage="<users_or_roles...> [options]", cooldown_after_parsing=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    @commands.cooldown(1, 600, BucketType.channel)
    async def removeuser(self, ctx, *users_arg: Union[discord.Member, discord.Role, str]):
        """Removes a user from a modmail thread

        `options` can be `silent` or `silently`.
        """
        silent = False
        users = []
        for u in users_arg:
            if isinstance(u, str):
                if "silent" in u or "silently" in u:
                    silent = True
            elif isinstance(u, discord.Role):
                users += u.members
            elif isinstance(u, discord.Member):
                users.append(u)

        for u in users:
            # u is a discord.Member
            curr_thread = await self.bot.threads.find(recipient=u)
            if ctx.thread != curr_thread:
                em = discord.Embed(
                    title="Error",
                    description=f"{u.mention} is not in this thread.",
                    color=self.bot.error_color,
                )
                await ctx.send(embed=em)
                ctx.command.reset_cooldown(ctx)
                return
            elif ctx.thread.recipient == u:
                em = discord.Embed(
                    title="Error",
                    description=f"{u.mention} is the main recipient of the thread and cannot be removed.",
                    color=self.bot.error_color,
                )
                await ctx.send(embed=em)
                ctx.command.reset_cooldown(ctx)
                return

        if not users:
            em = discord.Embed(
                title="Error",
                description="No valid users to remove.",
                color=self.bot.error_color,
            )
            await ctx.send(embed=em)
            ctx.command.reset_cooldown(ctx)
            return

        to_exec = []
        if not silent:
            description = self.bot.formatter.format(
                self.bot.config["private_removed_from_group_response"], moderator=ctx.author
            )
            em = discord.Embed(
                title=self.bot.config["private_removed_from_group_title"],
                description=description,
                color=self.bot.main_color,
            )
            if self.bot.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()
            em.set_footer(text=str(ctx.author), icon_url=ctx.author.display_avatar.url)
            for u in users:
                to_exec.append(u.send(embed=em))

            description = self.bot.formatter.format(
                self.bot.config["public_removed_from_group_response"],
                moderator=ctx.author,
                users=", ".join(u.name for u in users),
            )
            em = discord.Embed(
                title=self.bot.config["public_removed_from_group_title"],
                description=description,
                color=self.bot.main_color,
            )
            if self.bot.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()
            em.set_footer(text=f"{users[0]}", icon_url=users[0].display_avatar.url)

            for i in ctx.thread.recipients:
                if i not in users:
                    to_exec.append(i.send(embed=em))

        await ctx.thread.remove_users(users)
        if to_exec:
            await asyncio.gather(*to_exec)

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command(usage="<users_or_roles...> [options]", cooldown_after_parsing=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    @commands.cooldown(1, 600, BucketType.channel)
    async def anonadduser(self, ctx, *users_arg: Union[discord.Member, discord.Role, str]):
        """Adds a user to a modmail thread anonymously

        `options` can be `silent` or `silently`.
        """
        silent = False
        users = []
        for u in users_arg:
            if isinstance(u, str):
                if "silent" in u or "silently" in u:
                    silent = True
            elif isinstance(u, discord.Role):
                users += u.members
            elif isinstance(u, discord.Member):
                users.append(u)

        for u in users:
            curr_thread = await self.bot.threads.find(recipient=u)
            if curr_thread == ctx.thread:
                users.remove(u)
                continue

            if curr_thread:
                em = discord.Embed(
                    title="Error",
                    description=f"{u.mention} is already in a thread: {curr_thread.channel.mention}.",
                    color=self.bot.error_color,
                )
                await ctx.send(embed=em)
                ctx.command.reset_cooldown(ctx)
                return

        if not users:
            em = discord.Embed(
                title="Error",
                description="All users are already in the thread.",
                color=self.bot.error_color,
            )
            await ctx.send(embed=em)
            ctx.command.reset_cooldown(ctx)
            return

        to_exec = []
        if not silent:
            em = discord.Embed(
                title=self.bot.config["private_added_to_group_title"],
                description=self.bot.config["private_added_to_group_description_anon"],
                color=self.bot.main_color,
            )
            if self.bot.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()

            tag = self.bot.config["mod_tag"]
            if tag is None:
                tag = str(get_top_role(ctx.author, self.bot.config["use_hoisted_top_role"]))
            name = self.bot.config["anon_username"]
            if name is None:
                name = tag
            avatar_url = self.bot.config["anon_avatar_url"]
            if avatar_url is None:
                avatar_url = self.bot.get_guild_icon(guild=ctx.guild)
            em.set_footer(text=name, icon_url=avatar_url)

            for u in users:
                to_exec.append(u.send(embed=em))

            description = self.bot.formatter.format(
                self.bot.config["public_added_to_group_description_anon"],
                users=", ".join(u.name for u in users),
            )
            em = discord.Embed(
                title=self.bot.config["public_added_to_group_title"],
                description=description,
                color=self.bot.main_color,
            )
            if self.bot.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()
            em.set_footer(text=f"{users[0]}", icon_url=users[0].display_avatar.url)

            for i in ctx.thread.recipients:
                if i not in users:
                    to_exec.append(i.send(embed=em))

        await ctx.thread.add_users(users)
        if to_exec:
            await asyncio.gather(*to_exec)

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command(usage="<users_or_roles...> [options]", cooldown_after_parsing=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    @commands.cooldown(1, 600, BucketType.channel)
    async def anonremoveuser(self, ctx, *users_arg: Union[discord.Member, discord.Role, str]):
        """Removes a user from a modmail thread anonymously

        `options` can be `silent` or `silently`.
        """
        silent = False
        users = []
        for u in users_arg:
            if isinstance(u, str):
                if "silent" in u or "silently" in u:
                    silent = True
            elif isinstance(u, discord.Role):
                users += u.members
            elif isinstance(u, discord.Member):
                users.append(u)

        for u in users:
            curr_thread = await self.bot.threads.find(recipient=u)
            if ctx.thread != curr_thread:
                em = discord.Embed(
                    title="Error",
                    description=f"{u.mention} is not in this thread.",
                    color=self.bot.error_color,
                )
                await ctx.send(embed=em)
                ctx.command.reset_cooldown(ctx)
                return
            elif ctx.thread.recipient == u:
                em = discord.Embed(
                    title="Error",
                    description=f"{u.mention} is the main recipient of the thread and cannot be removed.",
                    color=self.bot.error_color,
                )
                await ctx.send(embed=em)
                ctx.command.reset_cooldown(ctx)
                return

        to_exec = []
        if not silent:
            em = discord.Embed(
                title=self.bot.config["private_removed_from_group_title"],
                description=self.bot.config["private_removed_from_group_description_anon"],
                color=self.bot.main_color,
            )
            if self.bot.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()

            tag = self.bot.config["mod_tag"]
            if tag is None:
                tag = str(get_top_role(ctx.author, self.bot.config["use_hoisted_top_role"]))
            name = self.bot.config["anon_username"]
            if name is None:
                name = tag
            avatar_url = self.bot.config["anon_avatar_url"]
            if avatar_url is None:
                avatar_url = self.bot.get_guild_icon(guild=ctx.guild)
            em.set_footer(text=name, icon_url=avatar_url)

            for u in users:
                to_exec.append(u.send(embed=em))

            description = self.bot.formatter.format(
                self.bot.config["public_removed_from_group_description_anon"],
                users=", ".join(u.name for u in users),
            )
            em = discord.Embed(
                title=self.bot.config["public_removed_from_group_title"],
                description=description,
                color=self.bot.main_color,
            )
            if self.bot.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()
            em.set_footer(text=f"{users[0]}", icon_url=users[0].display_avatar.url)

            for i in ctx.thread.recipients:
                if i not in users:
                    to_exec.append(i.send(embed=em))

        await ctx.thread.remove_users(users)
        if to_exec:
            await asyncio.gather(*to_exec)

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def logs(self, ctx, *, user: User = None):
        """
        Get previous Modmail thread logs of a member.

        Leave `user` blank when this command is used within a
        thread channel to show logs for the current recipient.
        `user` may be a user ID, mention, or name.
        """

        await ctx.typing()

        if not user:
            thread = ctx.thread
            if not thread:
                raise commands.MissingRequiredArgument(SimpleNamespace(name="member"))
            user = thread.recipient or await self.bot.get_or_fetch_user(thread.id)

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
        embeds = self.format_log_embeds(entries, avatar_url=self.bot.get_guild_icon(guild=ctx.guild))

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

        embeds = self.format_log_embeds(entries, avatar_url=self.bot.get_guild_icon(guild=ctx.guild))

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

        await ctx.typing()

        entries = await self.bot.api.search_by_text(query, limit)

        embeds = self.format_log_embeds(entries, avatar_url=self.bot.get_guild_icon(guild=ctx.guild))

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

    @commands.command(aliases=["formatanonreply"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def fareply(self, ctx, *, msg: str = ""):
        """
        Anonymously reply to a Modmail thread with variables.

        Works just like `{prefix}areply`, however with the addition of three variables:
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
            await ctx.thread.reply(ctx.message, anonymous=True)

    @commands.command(aliases=["formatplainreply"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def fpreply(self, ctx, *, msg: str = ""):
        """
        Reply to a Modmail thread with variables and a plain message.

        Works just like `{prefix}areply`, however with the addition of three variables:
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
            await ctx.thread.reply(ctx.message, plain=True)

    @commands.command(aliases=["formatplainanonreply"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def fpareply(self, ctx, *, msg: str = ""):
        """
        Anonymously reply to a Modmail thread with variables and a plain message.

        Works just like `{prefix}areply`, however with the addition of three variables:
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
            await ctx.thread.reply(ctx.message, anonymous=True, plain=True)

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

    @commands.command(aliases=["plainreply"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def preply(self, ctx, *, msg: str = ""):
        """
        Reply to a Modmail thread with a plain message.

        Supports attachments and images as well as
        automatically embedding image URLs.
        """
        ctx.message.content = msg
        async with ctx.typing():
            await ctx.thread.reply(ctx.message, plain=True)

    @commands.command(aliases=["plainanonreply", "plainanonymousreply"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def pareply(self, ctx, *, msg: str = ""):
        """
        Reply to a Modmail thread with a plain message and anonymously.

        Supports attachments and images as well as
        automatically embedding image URLs.
        """
        ctx.message.content = msg
        async with ctx.typing():
            await ctx.thread.reply(ctx.message, anonymous=True, plain=True)

    @commands.group(invoke_without_command=True)
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

    @note.command(name="persistent", aliases=["persist"])
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    @checks.thread_only()
    async def note_persistent(self, ctx, *, msg: str = ""):
        """
        Take a persistent note about the current user.
        """
        ctx.message.content = msg
        async with ctx.typing():
            msg = await ctx.thread.note(ctx.message, persistent=True)
            await msg.pin()
        await self.bot.api.create_note(recipient=ctx.thread.recipient, message=ctx.message, message_id=msg.id)

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
                    description="Cannot find a message to edit. Plain messages are not supported.",
                    color=self.bot.error_color,
                )
            )

        sent_emoji, _ = await self.bot.retrieve_emoji()
        await self.bot.add_reaction(ctx.message, sent_emoji)

    @commands.command()
    @checks.has_permissions(PermissionLevel.REGULAR)
    async def selfcontact(self, ctx):
        """Creates a thread with yourself"""
        await ctx.invoke(self.contact, users=[ctx.author])

    @commands.command(usage="<user> [category] [options]")
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def contact(
        self,
        ctx,
        users: commands.Greedy[
            Union[Literal["silent", "silently"], discord.Member, discord.User, discord.Role]
        ],
        *,
        category: SimilarCategoryConverter = None,
        manual_trigger=True,
    ):
        """
        Create a thread with a specified member.

        If `category` is specified, the thread
        will be created in that specified category.

        `category`, if specified, may be a category ID, mention, or name.
        `users` may be a user ID, mention, or name. If multiple users are specified, a group thread will start.
        A maximum of 5 users are allowed.
        `options` can be `silent` or `silently`.
        """
        silent = any(x in users for x in ("silent", "silently"))
        if silent:
            try:
                users.remove("silent")
            except ValueError:
                pass

            try:
                users.remove("silently")
            except ValueError:
                pass

        if isinstance(category, str):
            category = category.split()

            category = " ".join(category)
            if category:
                try:
                    category = await SimilarCategoryConverter().convert(
                        ctx, category
                    )  # attempt to find a category again
                except commands.BadArgument:
                    category = None

            if isinstance(category, str):
                category = None

        errors = []
        for u in list(users):
            if isinstance(u, discord.Role):
                users += u.members
                users.remove(u)

        for u in list(users):
            exists = await self.bot.threads.find(recipient=u)
            if exists:
                errors.append(f"A thread for {u} already exists.")
                if exists.channel:
                    errors[-1] += f" in {exists.channel.mention}"
                errors[-1] += "."
                users.remove(u)
            elif u.bot:
                errors.append(f"{u} is a bot, cannot add to thread.")
                users.remove(u)
            elif await self.bot.is_blocked(u):
                ref = f"{u.mention} is" if ctx.author != u else "You are"
                errors.append(f"{ref} currently blocked from contacting {self.bot.user.name}.")
                users.remove(u)

        if len(users) > 5:
            errors.append("Group conversations only support 5 users.")
            users = []

        if errors or not users:
            if not users:
                # no users left
                title = "Thread not created"
            else:
                title = None

            if manual_trigger:  # not react to contact
                embed = discord.Embed(title=title, color=self.bot.error_color, description="\n".join(errors))
                await ctx.send(embed=embed, delete_after=10)

            if not users:
                # end
                return

        creator = ctx.author if manual_trigger else users[0]

        thread = await self.bot.threads.create(
            recipient=users[0],
            creator=creator,
            category=category,
            manual_trigger=manual_trigger,
        )

        if thread.cancelled:
            return

        if self.bot.config["dm_disabled"] in (DMDisabled.NEW_THREADS, DMDisabled.ALL_THREADS):
            logger.info("Contacting user %s when Modmail DM is disabled.", users[0])

        if not silent and not self.bot.config.get("thread_contact_silently"):
            if creator.id == users[0].id:
                description = self.bot.config["thread_creation_self_contact_response"]
            else:
                description = self.bot.formatter.format(
                    self.bot.config["thread_creation_contact_response"], creator=creator
                )

            em = discord.Embed(
                title=self.bot.config["thread_creation_contact_title"],
                description=description,
                color=self.bot.main_color,
            )
            if self.bot.config["show_timestamp"]:
                em.timestamp = discord.utils.utcnow()
            em.set_footer(text=f"{creator}", icon_url=creator.display_avatar.url)

            for u in users:
                await u.send(embed=em)

        embed = discord.Embed(
            title="Created Thread",
            description=f"Thread started by {creator.mention} for {', '.join(u.mention for u in users)}.",
            color=self.bot.main_color,
        )
        await thread.wait_until_ready()

        if users[1:]:
            await thread.add_users(users[1:])

        await thread.channel.send(embed=embed)

        if manual_trigger:
            sent_emoji, _ = await self.bot.retrieve_emoji()
            await self.bot.add_reaction(ctx.message, sent_emoji)
            await asyncio.sleep(5)
            await ctx.message.delete()

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def blocked(self, ctx):
        """Retrieve a list of blocked users."""

        roles = []
        users = []
        now = ctx.message.created_at

        blocked_users = list(self.bot.blocked_users.items())
        for id_, reason in blocked_users:
            # parse "reason" and check if block is expired
            try:
                end_time, after = extract_block_timestamp(reason, id_)
            except ValueError:
                continue

            if end_time is not None:
                if after <= 0:
                    # No longer blocked
                    self.bot.blocked_users.pop(str(id_))
                    logger.debug("No longer blocked, user %s.", id_)
                    continue

            try:
                user = await self.bot.get_or_fetch_user(int(id_))
            except discord.NotFound:
                users.append((id_, reason))
            else:
                users.append((user.mention, reason))

        blocked_roles = list(self.bot.blocked_roles.items())
        for id_, reason in blocked_roles:
            # parse "reason" and check if block is expired
            # etc "blah blah blah... until 2019-10-14T21:12:45.559948."
            try:
                end_time, after = extract_block_timestamp(reason, id_)
            except ValueError:
                continue

            if end_time is not None:
                if after <= 0:
                    # No longer blocked
                    self.bot.blocked_roles.pop(str(id_))
                    logger.debug("No longer blocked, role %s.", id_)
                    continue

            role = self.bot.guild.get_role(int(id_))
            if role:
                roles.append((role.mention, reason))

        user_embeds = [discord.Embed(title="Blocked Users", color=self.bot.main_color, description="")]

        if users:
            embed = user_embeds[0]

            for mention, reason in users:
                line = mention + f" - {reason or 'No Reason Provided'}\n"
                if len(embed.description) + len(line) > 2048:
                    embed = discord.Embed(
                        title="Blocked Users",
                        color=self.bot.main_color,
                        description=line,
                    )
                    user_embeds.append(embed)
                else:
                    embed.description += line
        else:
            user_embeds[0].description = "Currently there are no blocked users."

        if len(user_embeds) > 1:
            for n, em in enumerate(user_embeds):
                em.title = f"{em.title} [{n + 1}]"

        role_embeds = [discord.Embed(title="Blocked Roles", color=self.bot.main_color, description="")]

        if roles:
            embed = role_embeds[-1]

            for mention, reason in roles:
                line = mention + f" - {reason or 'No Reason Provided'}\n"
                if len(embed.description) + len(line) > 2048:
                    role_embeds[-1].set_author()
                    embed = discord.Embed(
                        title="Blocked Roles",
                        color=self.bot.main_color,
                        description=line,
                    )
                    role_embeds.append(embed)
                else:
                    embed.description += line
        else:
            role_embeds[-1].description = "Currently there are no blocked roles."

        if len(role_embeds) > 1:
            for n, em in enumerate(role_embeds):
                em.title = f"{em.title} [{n + 1}]"

        session = EmbedPaginatorSession(ctx, *user_embeds, *role_embeds)

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
    async def block(
        self,
        ctx,
        user_or_role: Optional[Union[User, discord.Role]] = None,
        *,
        after: UserFriendlyTime = None,
    ):
        """
        Block a user or role from using Modmail.

        You may choose to set a time as to when the user will automatically be unblocked.

        Leave `user` blank when this command is used within a
        thread channel to block the current recipient.
        `user` may be a user ID, mention, or name.
        `duration` may be a simple "human-readable" time text. See `{prefix}help close` for examples.
        """

        if user_or_role is None:
            thread = ctx.thread
            if thread:
                user_or_role = thread.recipient
            elif after is None:
                raise commands.MissingRequiredArgument(SimpleNamespace(name="user or role"))
            else:
                raise commands.BadArgument(f'User or role "{after.arg}" not found.')

        mention = getattr(user_or_role, "mention", f"`{user_or_role.id}`")

        if (
            not isinstance(user_or_role, discord.Role)
            and str(user_or_role.id) in self.bot.blocked_whitelisted_users
        ):
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
                fmt_dt = discord.utils.format_dt(after.dt, "R")
            if after.dt > after.now:
                fmt_dt = discord.utils.format_dt(after.dt, "f")

            reason += f" until {fmt_dt}"

        reason += "."

        if isinstance(user_or_role, discord.Role):
            msg = self.bot.blocked_roles.get(str(user_or_role.id))
        else:
            msg = self.bot.blocked_users.get(str(user_or_role.id))

        if msg is None:
            msg = ""

        if msg:
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

        if isinstance(user_or_role, discord.Role):
            self.bot.blocked_roles[str(user_or_role.id)] = reason
        else:
            self.bot.blocked_users[str(user_or_role.id)] = reason
        await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.MODERATOR)
    @trigger_typing
    async def unblock(self, ctx, *, user_or_role: Union[User, Role] = None):
        """
        Unblock a user from using Modmail.

        Leave `user` blank when this command is used within a
        thread channel to unblock the current recipient.
        `user` may be a user ID, mention, or name.
        """

        if user_or_role is None:
            thread = ctx.thread
            if thread:
                user_or_role = thread.recipient
            else:
                raise commands.MissingRequiredArgument(SimpleNamespace(name="user"))

        mention = getattr(user_or_role, "mention", f"`{user_or_role.id}`")
        name = getattr(user_or_role, "name", f"`{user_or_role.id}`")

        if not isinstance(user_or_role, discord.Role) and str(user_or_role.id) in self.bot.blocked_users:
            msg = self.bot.blocked_users.pop(str(user_or_role.id)) or ""
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
                    f'Use "{self.bot.prefix}blocked whitelist {user_or_role.id}" to whitelist the user.'
                )
            else:
                embed = discord.Embed(
                    title="Success",
                    color=self.bot.main_color,
                    description=f"{mention} is no longer blocked.",
                )
        elif isinstance(user_or_role, discord.Role) and str(user_or_role.id) in self.bot.blocked_roles:
            msg = self.bot.blocked_roles.pop(str(user_or_role.id)) or ""
            await self.bot.config.update()

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
                    description="Cannot find a message to delete. Plain messages are not supported.",
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
                user_id = match_user_id(message.embeds[0].footer.text, any_string=True)
                other_recipients = match_other_recipients(ctx.channel.topic)
                for n, uid in enumerate(other_recipients):
                    other_recipients[n] = await self.bot.get_or_fetch_user(uid)

                if user_id != -1:
                    recipient = self.bot.get_user(user_id)
                    if recipient is None:
                        self.bot.threads.cache[user_id] = thread = Thread(
                            self.bot.threads, user_id, ctx.channel, other_recipients
                        )
                    else:
                        self.bot.threads.cache[user_id] = thread = Thread(
                            self.bot.threads, recipient, ctx.channel, other_recipients
                        )
                    thread.ready = True
                    logger.info("Setting current channel's topic to User ID and created new thread.")
                    await ctx.channel.edit(reason="Fix broken Modmail thread", topic=f"User ID: {user_id}")
                    return await self.bot.add_reaction(ctx.message, sent_emoji)

        else:
            logger.warning("No genesis message found.")

        # match username from channel name
        # username-1234, username-1234_1, username-1234_2
        m = re.match(r"^(.+)-(\d{4})(?:_\d+)?$", ctx.channel.name)
        if m is not None:
            users = set(
                filter(
                    lambda member: member.name == m.group(1) and member.discriminator == m.group(2),
                    ctx.guild.members,
                )
            )
            if len(users) == 1:
                user = users.pop()
                name = self.bot.format_channel_name(user, exclude_channel=ctx.channel)
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

                other_recipients = match_other_recipients(ctx.channel.topic)
                for n, uid in enumerate(other_recipients):
                    other_recipients[n] = await self.bot.get_or_fetch_user(uid)

                if recipient is None:
                    self.bot.threads.cache[user.id] = thread = Thread(
                        self.bot.threads, user_id, ctx.channel, other_recipients
                    )
                else:
                    self.bot.threads.cache[user.id] = thread = Thread(
                        self.bot.threads, recipient, ctx.channel, other_recipients
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

        if self.bot.config["dm_disabled"] != DMDisabled.NONE:
            self.bot.config["dm_disabled"] = DMDisabled.NONE
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
        if self.bot.config["dm_disabled"] < DMDisabled.NEW_THREADS:
            self.bot.config["dm_disabled"] = DMDisabled.NEW_THREADS
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

        if self.bot.config["dm_disabled"] != DMDisabled.ALL_THREADS:
            self.bot.config["dm_disabled"] = DMDisabled.ALL_THREADS
            await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def isenable(self, ctx):
        """
        Check if the DM functionalities of Modmail is enabled.
        """

        if self.bot.config["dm_disabled"] == DMDisabled.NEW_THREADS:
            embed = discord.Embed(
                title="New Threads Disabled",
                description="Modmail is not creating new threads.",
                color=self.bot.error_color,
            )
        elif self.bot.config["dm_disabled"] == DMDisabled.ALL_THREADS:
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


async def setup(bot):
    await bot.add_cog(Modmail(bot))
