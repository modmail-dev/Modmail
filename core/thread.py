import asyncio
import base64
import copy
import functools
import io
import re
import time
import traceback
import typing
import warnings
from datetime import timedelta, datetime, timezone
from types import SimpleNamespace

import isodate

import discord
from discord.ext.commands import MissingRequiredArgument, CommandError
from lottie.importers import importers as l_importers
from lottie.exporters import exporters as l_exporters

from core.models import DMDisabled, DummyMessage, getLogger
from core.time import human_timedelta
from core.utils import (
    is_image_url,
    parse_channel_topic,
    match_title,
    match_user_id,
    truncate,
    get_top_role,
    create_thread_channel,
    get_joint_id,
    AcceptButton,
    DenyButton,
    ConfirmThreadCreationView,
    DummyParam,
    extract_forwarded_content,
)

logger = getLogger(__name__)


class Thread:
    """Represents a discord Modmail thread"""

    def __init__(
        self,
        manager: "ThreadManager",
        recipient: typing.Union[discord.Member, discord.User, int],
        channel: typing.Union[discord.DMChannel, discord.TextChannel] = None,
        other_recipients: typing.List[typing.Union[discord.Member, discord.User]] = None,
    ):
        self.manager = manager
        self.bot = manager.bot
        if isinstance(recipient, int):
            self._id = recipient
            self._recipient = None
        else:
            if recipient.bot:
                raise CommandError("Recipient cannot be a bot.")
            self._id = recipient.id
            self._recipient = recipient
        self._other_recipients = other_recipients or []
        self._channel = channel
        self._genesis_message = None
        self._ready_event = asyncio.Event()
        self.wait_tasks = []
        self.close_task = None
        self.auto_close_task = None
        self._cancelled = False
        # --- SNOOZE STATE ---
        self.snoozed = False  # True if thread is snoozed
        self.snooze_data = None  # Dict with channel/category/position/messages for restoration
        self.log_key = None  # Ensure log_key always exists

    def __repr__(self):
        return f'Thread(recipient="{self.recipient or self.id}", channel={self.channel.id}, other_recipients={len(self._other_recipients)})'

    def __eq__(self, other):
        if isinstance(other, Thread):
            return self.id == other.id
        return super().__eq__(other)

    async def wait_until_ready(self) -> None:
        """Blocks execution until the thread is fully set up."""
        # timeout after 30 seconds
        task = self.bot.loop.create_task(asyncio.wait_for(self._ready_event.wait(), timeout=25))
        self.wait_tasks.append(task)
        try:
            await task
        except asyncio.TimeoutError:
            pass

        self.wait_tasks.remove(task)

    @property
    def id(self) -> int:
        return self._id

    @property
    def channel(self) -> typing.Union[discord.TextChannel, discord.DMChannel]:
        return self._channel

    @property
    def recipient(self) -> typing.Optional[typing.Union[discord.User, discord.Member]]:
        return self._recipient

    @property
    def recipients(self) -> typing.List[typing.Union[discord.User, discord.Member]]:
        return [self._recipient] + self._other_recipients

    @property
    def ready(self) -> bool:
        return self._ready_event.is_set()

    @ready.setter
    def ready(self, flag: bool):
        if flag:
            self._ready_event.set()
            self.bot.dispatch("thread_create", self)
        else:
            self._ready_event.clear()

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @cancelled.setter
    def cancelled(self, flag: bool):
        self._cancelled = flag
        if flag:
            for i in self.wait_tasks:
                i.cancel()

    async def snooze(self, moderator=None, command_used=None, snooze_for=None):
        """
        Save channel/category/position/messages to DB, mark as snoozed, delete channel.
        """
        if self.snoozed:
            return False  # Already snoozed
        channel = self.channel
        if not isinstance(channel, discord.TextChannel):
            return False
        # Ensure self.log_key is set before snoozing
        if not self.log_key:
            # Try to fetch from DB using channel_id
            log_entry = await self.bot.api.get_log(self.channel.id)
            if log_entry and "key" in log_entry:
                self.log_key = log_entry["key"]
            # Fallback: try by recipient id
            elif hasattr(self, "id"):
                log_entry = await self.bot.api.get_log(str(self.id))
                if log_entry and "key" in log_entry:
                    self.log_key = log_entry["key"]

        now = datetime.now(timezone.utc)
        self.snooze_data = {
            "category_id": channel.category_id,
            "position": channel.position,
            "name": channel.name,
            "topic": channel.topic,
            "slowmode_delay": channel.slowmode_delay,
            "nsfw": channel.nsfw,
            "overwrites": [(role.id, perm._values) for role, perm in channel.overwrites.items()],
            "messages": [
                {
                    "author_id": m.author.id,
                    "content": m.content,
                    "attachments": [a.url for a in m.attachments],
                    "embeds": [e.to_dict() for e in m.embeds],
                    "created_at": m.created_at.isoformat(),
                    "type": (
                        "mod_only"
                        if (
                            m.embeds
                            and getattr(m.embeds[0], "author", None)
                            and (
                                getattr(m.embeds[0].author, "name", "").startswith("📝 Note")
                                or getattr(m.embeds[0].author, "name", "").startswith("📝 Persistent Note")
                            )
                        )
                        else None
                    ),
                    "author_name": getattr(m.author, "name", None),
                }
                async for m in channel.history(limit=None, oldest_first=True)
                if not (
                    m.embeds
                    and getattr(m.embeds[0], "author", None)
                    and (
                        getattr(m.embeds[0].author, "name", "").startswith("📝 Note")
                        or getattr(m.embeds[0].author, "name", "").startswith("📝 Persistent Note")
                    )
                )
                and getattr(m, "type", None) not in ("internal", "note")
            ],
            "snoozed_by": getattr(moderator, "name", None) if moderator else None,
            "snooze_command": command_used,
            "log_key": self.log_key,
            "snooze_start": now.isoformat(),
            "snooze_for": snooze_for,
        }
        self.snoozed = True
        # Save to DB (robust: try recipient.id, then channel_id)
        result = await self.bot.api.logs.update_one(
            {"recipient.id": str(self.id)},
            {"$set": {"snoozed": True, "snooze_data": self.snooze_data}},
        )
        if result.modified_count == 0 and self.channel:
            result = await self.bot.api.logs.update_one(
                {"channel_id": str(self.channel.id)},
                {"$set": {"snoozed": True, "snooze_data": self.snooze_data}},
            )
        import logging

        logging.info(f"[SNOOZE] DB update result: {result.modified_count}")
        # Delete channel
        await channel.delete(reason="Thread snoozed by moderator")
        self._channel = None
        return True

    async def restore_from_snooze(self):
        """
        Recreate channel in original category/position, replay messages, mark as not snoozed.
        """
        if not self.snooze_data or not isinstance(self.snooze_data, dict):
            import logging

            logging.warning(
                f"[UNSNOOZE] Tried to restore thread {self.id} but snooze_data is None or not a dict."
            )
            return False
        # Now safe to access self.snooze_data
        snoozed_by = self.snooze_data.get("snoozed_by")
        snooze_command = self.snooze_data.get("snooze_command")
        guild = self.bot.modmail_guild
        category = guild.get_channel(self.snooze_data["category_id"])
        overwrites = {}
        for role_id, perm_values in self.snooze_data["overwrites"]:
            role = guild.get_role(role_id) or guild.get_member(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(**perm_values)
        channel = await guild.create_text_channel(
            name=self.snooze_data["name"],
            category=category,
            topic=self.snooze_data["topic"],
            slowmode_delay=self.snooze_data["slowmode_delay"],
            overwrites=overwrites,
            nsfw=self.snooze_data["nsfw"],
            position=self.snooze_data["position"],
            reason="Thread unsnoozed/restored",
        )
        self._channel = channel
        # Strictly restore the log_key from snooze_data (never create a new one)
        self.log_key = self.snooze_data.get("log_key")
        # Replay messages
        for msg in self.snooze_data["messages"]:
            author = self.bot.get_user(msg["author_id"]) or await self.bot.get_or_fetch_user(msg["author_id"])
            content = msg["content"]
            embeds = [discord.Embed.from_dict(e) for e in msg.get("embeds", []) if e]
            attachments = msg.get("attachments", [])
            msg_type = msg.get("type")
            # Only send if there is content, embeds, or attachments
            if not content and not embeds and not attachments:
                continue  # Skip empty messages
            author_is_mod = msg["author_id"] not in [r.id for r in self.recipients]
            if author_is_mod:
                username = msg.get("author_name") or (getattr(author, "name", None)) or "Unknown"
                user_id = msg.get("author_id")
                if embeds:
                    embeds[0].set_author(
                        name=f"{username} ({user_id})",
                        icon_url=(
                            author.display_avatar.url
                            if author and hasattr(author, "display_avatar")
                            else None
                        ),
                    )
                    await channel.send(embeds=embeds)
                else:
                    formatted = (
                        f"**{username} ({user_id})**: {content}" if content else f"**{username} ({user_id})**"
                    )
                    await channel.send(formatted)
            else:
                await channel.send(content=content or None, embeds=embeds or None)
        self.snoozed = False
        # Store snooze_data for notification before clearing
        snooze_data_for_notify = self.snooze_data
        self.snooze_data = None
        # Update channel_id in DB and clear snooze_data (robust: try log_key first)
        if self.log_key:
            result = await self.bot.api.logs.update_one(
                {"key": self.log_key},
                {"$set": {"channel_id": str(channel.id)}, "$unset": {"snoozed": "", "snooze_data": ""}},
            )
        else:
            result = await self.bot.api.logs.update_one(
                {"recipient.id": str(self.id)},
                {"$set": {"channel_id": str(channel.id)}, "$unset": {"snoozed": "", "snooze_data": ""}},
            )
            if result.modified_count == 0:
                result = await self.bot.api.logs.update_one(
                    {"channel_id": str(channel.id)},
                    {
                        "$set": {"channel_id": str(channel.id)},
                        "$unset": {"snoozed": "", "snooze_data": ""},
                    },
                )
        import logging

        logging.info(f"[UNSNOOZE] DB update result: {result.modified_count}")
        # Notify in the configured channel
        notify_channel = self.bot.config.get("unsnooze_notify_channel") or "thread"
        notify_text = self.bot.config.get("unsnooze_text") or "This thread has been unsnoozed and restored."
        if notify_channel == "thread":
            await channel.send(notify_text)
        else:
            ch = self.bot.get_channel(int(notify_channel))
            if ch:
                await ch.send(f"Thread for user <@{self.id}> has been unsnoozed and restored.")
        # Show who ran the snooze command and the command used
        # Use snooze_data_for_notify to avoid accessing self.snooze_data after it is set to None
        snoozed_by = snooze_data_for_notify.get("snoozed_by") if snooze_data_for_notify else None
        snooze_command = snooze_data_for_notify.get("snooze_command") if snooze_data_for_notify else None
        if snoozed_by or snooze_command:
            info = f"Snoozed by: {snoozed_by or 'Unknown'} | Command: {snooze_command or '?snooze'}"
            await channel.send(info)
        return True

    @classmethod
    async def from_channel(cls, manager: "ThreadManager", channel: discord.TextChannel) -> "Thread":
        # there is a chance it grabs from another recipient's main thread
        _, recipient_id, other_ids = parse_channel_topic(channel.topic)

        if recipient_id in manager.cache:
            thread = manager.cache[recipient_id]
        else:
            recipient = await manager.bot.get_or_fetch_user(recipient_id)

            other_recipients = []
            for uid in other_ids:
                try:
                    other_recipient = await manager.bot.get_or_fetch_user(uid)
                except discord.NotFound:
                    continue
                other_recipients.append(other_recipient)

            thread = cls(manager, recipient or recipient_id, channel, other_recipients)

        return thread

    async def get_genesis_message(self) -> discord.Message:
        if self._genesis_message is None:
            async for m in self.channel.history(limit=5, oldest_first=True):
                if m.author == self.bot.user:
                    if m.embeds and m.embeds[0].fields and m.embeds[0].fields[0].name == "Roles":
                        self._genesis_message = m

        return self._genesis_message

    async def setup(self, *, creator=None, category=None, initial_message=None):
        """Create the thread channel and other io related initialisation tasks"""
        self.bot.dispatch("thread_initiate", self, creator, category, initial_message)
        recipient = self.recipient

        # in case it creates a channel outside of category
        overwrites = {self.bot.modmail_guild.default_role: discord.PermissionOverwrite(read_messages=False)}

        category = category or self.bot.main_category

        if category is not None:
            overwrites = {}

        try:
            channel = await create_thread_channel(self.bot, recipient, category, overwrites)
        except discord.HTTPException as e:  # Failed to create due to missing perms.
            logger.critical("An error occurred while creating a thread.", exc_info=True)
            self.manager.cache.pop(self.id)

            embed = discord.Embed(color=self.bot.error_color)
            embed.title = "Error while trying to create a thread."
            embed.description = str(e)
            embed.add_field(name="Recipient", value=recipient.mention)

            if self.bot.log_channel is not None:
                await self.bot.log_channel.send(embed=embed)
            return

        self._channel = channel

        try:
            log_url, log_data = await asyncio.gather(
                self.bot.api.create_log_entry(recipient, channel, creator or recipient),
                self.bot.api.get_user_logs(recipient.id),
            )

            log_count = sum(1 for log in log_data if not log["open"])
        except Exception:
            logger.error("An error occurred while posting logs to the database.", exc_info=True)
            log_url = log_count = None
            # ensure core functionality still works

        self.ready = True

        if creator is not None and creator != recipient:
            mention = None
        else:
            mention = self.bot.config["mention"]

        async def send_genesis_message():
            info_embed = self._format_info_embed(recipient, log_url, log_count, self.bot.main_color)
            try:
                msg = await channel.send(mention, embed=info_embed)
                self.bot.loop.create_task(msg.pin())
                self._genesis_message = msg
            except Exception:
                logger.error("Failed unexpectedly:", exc_info=True)

        async def send_recipient_genesis_message():
            # Once thread is ready, tell the recipient (don't send if using contact on others)
            thread_creation_response = self.bot.config["thread_creation_response"]

            embed = discord.Embed(
                color=self.bot.mod_color,
                description=thread_creation_response,
                timestamp=channel.created_at,
            )

            recipient_thread_close = self.bot.config.get("recipient_thread_close")

            if recipient_thread_close:
                footer = self.bot.config["thread_self_closable_creation_footer"]
            else:
                footer = self.bot.config["thread_creation_footer"]

            embed.set_footer(
                text=footer, icon_url=self.bot.get_guild_icon(guild=self.bot.modmail_guild, size=128)
            )
            embed.title = self.bot.config["thread_creation_title"]

            if creator is None or creator == recipient:
                msg = await recipient.send(embed=embed)

                if recipient_thread_close:
                    close_emoji = self.bot.config["close_emoji"]
                    close_emoji = await self.bot.convert_emoji(close_emoji)
                    await self.bot.add_reaction(msg, close_emoji)

        async def send_persistent_notes():
            notes = await self.bot.api.find_notes(self.recipient)
            ids = {}

            class State:
                def store_user(self, user, cache):
                    return user

            for note in notes:
                author = note["author"]

                class Author:
                    name = author["name"]
                    id = author["id"]
                    discriminator = author["discriminator"]
                    display_avatar = SimpleNamespace(url=author["avatar_url"])

                data = {
                    "id": round(time.time() * 1000 - discord.utils.DISCORD_EPOCH) << 22,
                    "attachments": {},
                    "embeds": {},
                    "edited_timestamp": None,
                    "type": None,
                    "pinned": None,
                    "mention_everyone": None,
                    "tts": None,
                    "content": note["message"],
                    "author": Author(),
                }
                message = discord.Message(state=State(), channel=self.channel, data=data)
                ids[note["_id"]] = str((await self.note(message, persistent=True, thread_creation=True)).id)

            await self.bot.api.update_note_ids(ids)

        async def activate_auto_triggers():
            if initial_message:
                message = DummyMessage(copy.copy(initial_message))

                try:
                    return await self.bot.trigger_auto_triggers(message, channel)
                except RuntimeError:
                    pass

        await asyncio.gather(
            send_genesis_message(),
            send_recipient_genesis_message(),
            activate_auto_triggers(),
            send_persistent_notes(),
        )
        self.bot.dispatch("thread_ready", self, creator, category, initial_message)

    def _format_info_embed(self, user, log_url, log_count, color):
        """Get information about a member of a server
        supports users from the guild or not."""
        member = self.bot.guild.get_member(user.id)
        time = discord.utils.utcnow()

        # key = log_url.split('/')[-1]

        role_names = ""
        if member is not None and self.bot.config["thread_show_roles"]:
            sep_server = self.bot.using_multiple_server_setup
            separator = ", " if sep_server else " "

            roles = []

            for role in sorted(member.roles, key=lambda r: r.position):
                if role.is_default():
                    # @everyone
                    continue

                fmt = role.name if sep_server else role.mention
                roles.append(fmt)

                if len(separator.join(roles)) > 1024:
                    roles.append("...")
                    while len(separator.join(roles)) > 1024:
                        roles.pop(-2)
                    break

            role_names = separator.join(roles)

        user_info = []
        if self.bot.config["thread_show_account_age"]:
            created = discord.utils.format_dt(user.created_at, "R")
            user_info.append(f" was created {created}")

        embed = discord.Embed(color=color, description=user.mention, timestamp=time)

        if user.dm_channel:
            footer = f"User ID: {user.id} • DM ID: {user.dm_channel.id}"
        else:
            footer = f"User ID: {user.id}"

        if member is not None:
            embed.set_author(name=str(user), icon_url=member.display_avatar.url, url=log_url)

            if self.bot.config["thread_show_join_age"]:
                joined = discord.utils.format_dt(member.joined_at, "R")
                user_info.append(f"joined {joined}")

            if member.nick:
                embed.add_field(name="Nickname", value=member.nick, inline=True)
            if role_names:
                embed.add_field(name="Roles", value=role_names, inline=True)
            embed.set_footer(text=footer)
        else:
            embed.set_author(name=str(user), icon_url=user.display_avatar.url, url=log_url)
            embed.set_footer(text=f"{footer} • (not in main server)")

        embed.description += ", ".join(user_info)

        if log_count is not None:
            connector = "with" if user_info else "has"
            thread = "thread" if log_count == 1 else "threads"
            embed.description += f" {connector} **{log_count or 'no'}** past {thread}."
        else:
            embed.description += "."

        mutual_guilds = [g for g in self.bot.guilds if user in g.members]
        if member is None or len(mutual_guilds) > 1:
            embed.add_field(name="Mutual Server(s)", value=", ".join(g.name for g in mutual_guilds))

        return embed

    async def _close_after(self, after, closer, silent, delete_channel, message):
        await asyncio.sleep(after)
        return self.bot.loop.create_task(self._close(closer, silent, delete_channel, message, True))

    async def close(
        self,
        *,
        closer: typing.Union[discord.Member, discord.User],
        after: int = 0,
        silent: bool = False,
        delete_channel: bool = True,
        message: str = None,
        auto_close: bool = False,
    ) -> None:
        """Close a thread now or after a set time in seconds"""

        # restarts the after timer
        await self.cancel_closure(auto_close)

        if after > 0:
            # TODO: Add somewhere to clean up broken closures
            #  (when channel is already deleted)
            now = discord.utils.utcnow()
            items = {
                # 'initiation_time': now.isoformat(),
                "time": (now + timedelta(seconds=after)).isoformat(),
                "closer_id": closer.id,
                "silent": silent,
                "delete_channel": delete_channel,
                "message": message,
                "auto_close": auto_close,
            }
            self.bot.config["closures"][str(self.id)] = items
            await self.bot.config.update()

            task = asyncio.create_task(self._close_after(after, closer, silent, delete_channel, message))

            if auto_close:
                self.auto_close_task = task
            else:
                self.close_task = task
        else:
            await self._close(closer, silent, delete_channel, message)

    async def _close(self, closer, silent=False, delete_channel=True, message=None, scheduled=False):
        if self.channel:
            self.manager.closing.add(self.channel.id)
        try:
            self.manager.cache.pop(self.id)
        except KeyError as e:
            logger.error("Thread already closed: %s.", e)
            return

        await self.cancel_closure(all=True)

        # Cancel auto closing the thread if closed by any means.

        self.bot.config["subscriptions"].pop(str(self.id), None)
        self.bot.config["notification_squad"].pop(str(self.id), None)

        # Logging
        if self.channel:
            log_data = await self.bot.api.post_log(
                self.channel.id,
                {
                    "open": False,
                    "title": match_title(self.channel.topic),
                    "closed_at": str(discord.utils.utcnow()),
                    "nsfw": self.channel.nsfw,
                    "close_message": message,
                    "closer": {
                        "id": str(closer.id),
                        "name": closer.name,
                        "discriminator": closer.discriminator,
                        "avatar_url": closer.display_avatar.url,
                        "mod": True,
                    },
                },
            )
        else:
            log_data = None

        if isinstance(log_data, dict):
            prefix = self.bot.config["log_url_prefix"].strip("/")
            if prefix == "NONE":
                prefix = ""
            log_url = (
                f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{log_data['key']}"
            )

            if log_data["title"]:
                sneak_peak = log_data["title"]
            elif log_data["messages"]:
                content = str(log_data["messages"][0]["content"])
                sneak_peak = content.replace("\n", "")
            else:
                sneak_peak = "No content"

            if self.channel.nsfw:
                _nsfw = "NSFW-"
            else:
                _nsfw = ""

            desc = f"[`{_nsfw}{log_data['key']}`]({log_url}): "
            desc += truncate(sneak_peak, max=75 - 13)
        else:
            desc = "Could not resolve log url."
            log_url = None

        embed = discord.Embed(description=desc, color=self.bot.error_color)

        if self.recipient is not None:
            user = f"{self.recipient} (`{self.id}`)"
        else:
            user = f"`{self.id}`"

        if self.id == closer.id:
            _closer = "the Recipient"
        else:
            _closer = f"{closer} ({closer.id})"

        embed.title = user

        event = "Thread Closed as Scheduled" if scheduled else "Thread Closed"
        # embed.set_author(name=f"Event: {event}", url=log_url)
        embed.set_footer(text=f"{event} by {_closer}", icon_url=closer.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()

        tasks = [self.bot.config.update()]

        if self.bot.log_channel is not None and self.channel is not None:
            if self.bot.config["show_log_url_button"]:
                view = discord.ui.View()
                view.add_item(discord.ui.Button(label="Log link", url=log_url, style=discord.ButtonStyle.url))
            else:
                view = None
            tasks.append(self.bot.log_channel.send(embed=embed, view=view))

        # Thread closed message

        embed = discord.Embed(
            title=self.bot.config["thread_close_title"],
            color=self.bot.error_color,
        )
        if self.bot.config["show_timestamp"]:
            embed.timestamp = discord.utils.utcnow()

        if not message:
            if self.id == closer.id:
                message = self.bot.config["thread_self_close_response"]
            else:
                message = self.bot.config["thread_close_response"]

        message = self.bot.formatter.format(
            message, closer=closer, loglink=log_url, logkey=log_data["key"] if log_data else None
        )

        embed.description = message
        footer = self.bot.config["thread_close_footer"]
        embed.set_footer(text=footer, icon_url=self.bot.get_guild_icon(guild=self.bot.guild, size=128))

        if not silent:
            for user in self.recipients:
                if not message:
                    if user.id == closer.id:
                        message = self.bot.config["thread_self_close_response"]
                    else:
                        message = self.bot.config["thread_close_response"]
                    embed.description = message

                if user is not None:
                    tasks.append(user.send(embed=embed))

        if delete_channel and self.channel:
            tasks.append(self.channel.delete())

        try:
            await asyncio.gather(*tasks)
        finally:
            if self.channel:
                self.manager.closing.discard(self.channel.id)

        self.bot.dispatch("thread_close", self, closer, silent, delete_channel, message, scheduled)

    async def cancel_closure(self, auto_close: bool = False, all: bool = False) -> None:
        if self.close_task is not None and (not auto_close or all):
            self.close_task.cancel()
            self.close_task = None
        if self.auto_close_task is not None and (auto_close or all):
            self.auto_close_task.cancel()
            self.auto_close_task = None

        to_update = self.bot.config["closures"].pop(str(self.id), None)
        if to_update is not None:
            await self.bot.config.update()

    async def _restart_close_timer(self):
        """
        This will create or restart a timer to automatically close this
        thread.
        """
        timeout = self.bot.config.get("thread_auto_close")

        # Exit if timeout was not set
        if timeout == isodate.Duration():
            return

        # Set timeout seconds
        seconds = timeout.total_seconds()
        # seconds = 20  # Uncomment to debug with just 20 seconds
        reset_time = discord.utils.utcnow() + timedelta(seconds=seconds)
        human_time = discord.utils.format_dt(reset_time)

        if self.bot.config.get("thread_auto_close_silently"):
            return await self.close(closer=self.bot.user, silent=True, after=int(seconds), auto_close=True)

        # Grab message
        close_message = self.bot.formatter.format(
            self.bot.config["thread_auto_close_response"], timeout=human_time
        )

        time_marker_regex = "%t"
        if len(re.findall(time_marker_regex, close_message)) == 1:
            close_message = re.sub(time_marker_regex, str(human_time), close_message)
        elif len(re.findall(time_marker_regex, close_message)) > 1:
            logger.warning(
                "The thread_auto_close_response should only contain one '%s' to specify time.",
                time_marker_regex,
            )

        await self.close(closer=self.bot.user, after=int(seconds), message=close_message, auto_close=True)

    async def find_linked_messages(
        self,
        message_id: typing.Optional[int] = None,
        either_direction: bool = False,
        message1: discord.Message = None,
        note: bool = True,
    ) -> typing.Tuple[discord.Message, typing.List[typing.Optional[discord.Message]]]:
        if message1 is not None:
            if not message1.embeds or not message1.embeds[0].author.url or message1.author != self.bot.user:
                raise ValueError("Malformed thread message.")

        elif message_id is not None:
            try:
                message1 = await self.channel.fetch_message(message_id)
            except discord.NotFound:
                raise ValueError("Thread message not found.")

            if not (
                message1.embeds
                and message1.embeds[0].author.url
                and message1.embeds[0].color
                and message1.author == self.bot.user
            ):
                raise ValueError("Thread message not found.")

            if message1.embeds[0].footer and "Internal Message" in message1.embeds[0].footer.text:
                if not note:
                    raise ValueError("Thread message not found.")
                return message1, None

            if message1.embeds[0].color.value != self.bot.mod_color and not (
                either_direction and message1.embeds[0].color.value == self.bot.recipient_color
            ):
                raise ValueError("Thread message not found.")
        else:
            async for message1 in self.channel.history():
                if (
                    message1.embeds
                    and message1.embeds[0].author.url
                    and message1.embeds[0].color
                    and (
                        message1.embeds[0].color.value == self.bot.mod_color
                        or (either_direction and message1.embeds[0].color.value == self.bot.recipient_color)
                    )
                    and message1.embeds[0].author.url.split("#")[-1].isdigit()
                    and message1.author == self.bot.user
                ):
                    break
            else:
                raise ValueError("Thread message not found.")

        try:
            joint_id = int(message1.embeds[0].author.url.split("#")[-1])
        except ValueError:
            raise ValueError("Malformed thread message.")

        messages = [message1]
        for user in self.recipients:
            async for msg in user.history():
                if either_direction:
                    if msg.id == joint_id:
                        return message1, msg

                if not (msg.embeds and msg.embeds[0].author.url):
                    continue
                try:
                    if int(msg.embeds[0].author.url.split("#")[-1]) == joint_id:
                        messages.append(msg)
                        break
                except ValueError:
                    continue

        if len(messages) > 1:
            return messages

        raise ValueError("DM message not found.")

    async def edit_message(self, message_id: typing.Optional[int], message: str) -> None:
        try:
            message1, *message2 = await self.find_linked_messages(message_id)
        except ValueError:
            logger.warning("Failed to edit message.", exc_info=True)
            raise

        embed1 = message1.embeds[0]
        embed1.description = message

        tasks = [self.bot.api.edit_message(message1.id, message), message1.edit(embed=embed1)]
        if message1.embeds[0].footer and "Persistent Internal Message" in message1.embeds[0].footer.text:
            tasks += [self.bot.api.edit_note(message1.id, message)]
        else:
            for m2 in message2:
                if m2 is not None:
                    embed2 = m2.embeds[0]
                    embed2.description = message
                    tasks += [m2.edit(embed=embed2)]

        await asyncio.gather(*tasks)

    async def delete_message(
        self, message: typing.Union[int, discord.Message] = None, note: bool = True
    ) -> None:
        if isinstance(message, discord.Message):
            message1, *message2 = await self.find_linked_messages(message1=message, note=note)
        else:
            message1, *message2 = await self.find_linked_messages(message, note=note)
        tasks = []

        if not isinstance(message, discord.Message):
            tasks += [message1.delete()]

        for m2 in message2:
            if m2 is not None:
                tasks += [m2.delete()]

        if message1.embeds[0].footer and "Persistent Internal Message" in message1.embeds[0].footer.text:
            tasks += [self.bot.api.delete_note(message1.id)]

        if tasks:
            await asyncio.gather(*tasks)

    async def find_linked_message_from_dm(
        self, message, either_direction=False, get_thread_channel=False
    ) -> typing.List[discord.Message]:
        joint_id = None
        if either_direction:
            joint_id = get_joint_id(message)
            # could be None too, if that's the case we'll reassign this variable from
            # thread message we fetch in the next step

        linked_messages = []
        if self.channel is not None:
            async for msg in self.channel.history():
                if not msg.embeds:
                    continue

                msg_joint_id = get_joint_id(msg)
                if msg_joint_id is None:
                    continue

                if msg_joint_id == message.id:
                    linked_messages.append(msg)
                    break

                if joint_id is not None and msg_joint_id == joint_id:
                    linked_messages.append(msg)
                    break
            else:
                raise ValueError("Thread channel message not found.")
        else:
            raise ValueError("Thread channel message not found.")

        if get_thread_channel:
            # end early as we only want the main message from thread channel
            return linked_messages

        if joint_id is None:
            joint_id = get_joint_id(linked_messages[0])
            if joint_id is None:
                # still None, supress this and return the thread message
                logger.error("Malformed thread message.")
                return linked_messages

        for user in self.recipients:
            if user.dm_channel == message.channel:
                continue
            async for other_msg in user.history():
                if either_direction:
                    if other_msg.id == joint_id:
                        linked_messages.append(other_msg)
                        break

                if not other_msg.embeds:
                    continue

                other_joint_id = get_joint_id(other_msg)
                if other_joint_id is not None and other_joint_id == joint_id:
                    linked_messages.append(other_msg)
                    break
            else:
                logger.error("Linked message from recipient %s not found.", user)

        return linked_messages

    async def edit_dm_message(self, message: discord.Message, content: str) -> None:
        try:
            linked_messages = await self.find_linked_message_from_dm(message)
        except ValueError:
            logger.warning("Failed to edit message.", exc_info=True)
            raise

        for msg in linked_messages:
            embed = msg.embeds[0]
            if isinstance(msg.channel, discord.TextChannel):
                # just for thread channel, we put the old message in embed field
                embed.add_field(name="**Edited, former message:**", value=embed.description)
            embed.description = content
            await asyncio.gather(self.bot.api.edit_message(message.id, content), msg.edit(embed=embed))

    async def note(
        self, message: discord.Message, persistent=False, thread_creation=False
    ) -> discord.Message:
        if not message.content and not message.attachments and not message.stickers:
            raise MissingRequiredArgument(DummyParam("msg"))

        msg = await self.send(
            message,
            self.channel,
            note=True,
            persistent_note=persistent,
            thread_creation=thread_creation,
        )

        # Log as 'note' type for logviewer
        self.bot.loop.create_task(
            self.bot.api.append_log(message, message_id=msg.id, channel_id=self.channel.id, type_="note")
        )

        return msg

    async def reply(
        self, message: discord.Message, anonymous: bool = False, plain: bool = False
    ) -> typing.Tuple[typing.List[discord.Message], discord.Message]:
        """Returns List[user_dm_msg] and thread_channel_msg"""
        if not message.content and not message.attachments and not message.stickers:
            raise MissingRequiredArgument(DummyParam("msg"))
        for guild in self.bot.guilds:
            try:
                if await self.bot.get_or_fetch_member(guild, self.id):
                    break
            except discord.NotFound:
                pass
        else:
            return await message.channel.send(
                embed=discord.Embed(
                    color=self.bot.error_color,
                    description="Your message could not be delivered since "
                    "the recipient shares no servers with the bot.",
                )
            )

        user_msg_tasks = []
        tasks = []

        for user in self.recipients:
            user_msg_tasks.append(
                self.send(
                    message,
                    destination=user,
                    from_mod=True,
                    anonymous=anonymous,
                    plain=plain,
                )
            )

        try:
            user_msg = await asyncio.gather(*user_msg_tasks)
        except Exception as e:
            logger.error("Message delivery failed:", exc_info=True)
            user_msg = None
            if isinstance(e, discord.Forbidden):
                description = (
                    "Your message could not be delivered as "
                    "the recipient is only accepting direct "
                    "messages from friends, or the bot was "
                    "blocked by the recipient."
                )
            else:
                description = (
                    "Your message could not be delivered due "
                    "to an unknown error. Check `?debug` for "
                    "more information"
                )
            msg = await message.channel.send(
                embed=discord.Embed(
                    color=self.bot.error_color,
                    description=description,
                )
            )
        else:
            # Send the same thing in the thread channel.
            msg = await self.send(
                message, destination=self.channel, from_mod=True, anonymous=anonymous, plain=plain
            )

            tasks.append(
                self.bot.api.append_log(
                    message,
                    message_id=msg.id,
                    channel_id=self.channel.id,
                    type_="anonymous" if anonymous else "thread_message",
                )
            )

            # Cancel closing if a thread message is sent.
            if self.close_task is not None:
                await self.cancel_closure()
                tasks.append(
                    self.channel.send(
                        embed=discord.Embed(
                            color=self.bot.error_color,
                            description="Scheduled close has been cancelled.",
                        )
                    )
                )

        await asyncio.gather(*tasks)
        self.bot.dispatch("thread_reply", self, True, message, anonymous, plain)
        return (user_msg, msg)  # sent_to_user, sent_to_thread_channel

    async def send(
        self,
        message: discord.Message,
        destination: typing.Union[
            discord.TextChannel, discord.DMChannel, discord.User, discord.Member
        ] = None,
        from_mod: bool = False,
        note: bool = False,
        anonymous: bool = False,
        plain: bool = False,
        persistent_note: bool = False,
        thread_creation: bool = False,
    ) -> None:
        # Handle notes with Discord-like system message format - return early
        if note:
            destination = destination or self.channel
            content = message.content or "[No content]"

            # Create embed for note with Discord system message style
            embed = discord.Embed(
                description=content, color=0x5865F2  # Discord blurple color for system messages
            )

            # Set author with note icon and username
            if persistent_note:
                note_type = "Persistent Note"
            else:
                note_type = "Note"

            embed.set_author(
                name=f"📝 {note_type} ({message.author.name})", icon_url=message.author.display_avatar.url
            )

            # Add timestamp if enabled
            if self.bot.config["show_timestamp"]:
                embed.timestamp = message.created_at

            # Add a subtle footer to distinguish from replies
            if persistent_note:
                embed.set_footer(text="Persistent Internal Note")
            else:
                embed.set_footer(text="Internal Note")

            return await destination.send(embed=embed)

        if not note and from_mod:
            self.bot.loop.create_task(self._restart_close_timer())  # Start or restart thread auto close

        if self.close_task is not None:
            # cancel closing if a thread message is sent.
            self.bot.loop.create_task(self.cancel_closure())
            self.bot.loop.create_task(
                self.channel.send(
                    embed=discord.Embed(
                        color=self.bot.error_color,
                        description="Scheduled close has been cancelled.",
                    )
                )
            )

        if not self.ready:
            await self.wait_until_ready()

        if not from_mod and not note:
            self.bot.loop.create_task(self.bot.api.append_log(message, channel_id=self.channel.id))

        destination = destination or self.channel

        if destination is None:
            logger.error("Attempted to send a message to a thread with no channel (destination is None).")
            return
        try:
            await destination.typing()
        except discord.NotFound:
            logger.warning("Channel not found when trying to send message.")
            return

        author = message.author
        member = self.bot.guild.get_member(author.id)
        if member:
            avatar_url = member.display_avatar.url
        else:
            avatar_url = author.display_avatar.url

        # Handle forwarded messages first
        forwarded_jump_url = None
        if hasattr(message, "message_snapshots") and len(message.message_snapshots) > 0:
            snap = message.message_snapshots[0]
            # Only show "No content" if there's truly no content (no text, attachments, embeds, or stickers)
            if not snap.content and not message.attachments and not message.embeds and not message.stickers:
                content = "No content"
            else:
                content = snap.content or ""

            # Get jump_url from cached_message, fetch if not cached
            if hasattr(snap, "cached_message") and snap.cached_message is not None:
                forwarded_jump_url = snap.cached_message.jump_url
            else:
                if (
                    hasattr(message, "reference")
                    and message.reference
                    and message.reference.type == discord.MessageReferenceType.forward
                ):
                    try:
                        original_msg_channel = self.bot.get_channel(message.reference.channel_id)
                        original_msg = await original_msg_channel.fetch_message(message.reference.message_id)
                        forwarded_jump_url = original_msg.jump_url
                    except (discord.NotFound, discord.Forbidden, AttributeError):
                        pass

            content = f"📨 **Forwarded message:**\n{content}" if content else "📨 **Forwarded message:**"
        else:
            # Only show "No content" if there's truly no content (no text, attachments, embeds, or stickers)
            if (
                not message.content
                and not message.attachments
                and not message.embeds
                and not message.stickers
            ):
                content = "No content"
            else:
                content = message.content or ""

        # Only set description if there's actual content to show
        if content:
            embed = discord.Embed(description=content)
        else:
            embed = discord.Embed()
        if self.bot.config["show_timestamp"]:
            embed.timestamp = message.created_at

        # Add forwarded message context
        if forwarded_jump_url:
            embed.add_field(name="Context", value=f"- {forwarded_jump_url}", inline=True)

        system_avatar_url = "https://discordapp.com/assets/f78426a064bc9dd24847519259bc42af.png"

        if not note:
            if anonymous and from_mod and not isinstance(destination, discord.TextChannel):
                # Anonymously sending to the user.
                tag = self.bot.config["mod_tag"]
                if tag is None:
                    tag = str(get_top_role(author, self.bot.config["use_hoisted_top_role"]))
                name = self.bot.config["anon_username"]
                if name is None:
                    name = tag
                avatar_url = self.bot.config["anon_avatar_url"]
                if avatar_url is None:
                    avatar_url = self.bot.get_guild_icon(guild=self.bot.guild, size=128)
                embed.set_author(
                    name=name,
                    icon_url=avatar_url,
                    url=f"https://discordapp.com/channels/{self.bot.guild.id}#{message.id}",
                )
            else:
                # Normal message
                name = str(author)
                avatar_url = avatar_url
                embed.set_author(
                    name=name,
                    icon_url=avatar_url,
                    url=f"https://discordapp.com/users/{author.id}#{message.id}",
                )
        else:
            # Notes use system message style with note icon
            if persistent_note:
                note_type = "Persistent Note"
            else:
                note_type = "Note"

            embed.set_author(
                name=f"📝 {note_type} ({str(author)})",
                icon_url=avatar_url,
                url=f"https://discordapp.com/users/{author.id}#{message.id}",
            )
            embed.color = 0x5865F2  # Discord blurple for system messages

        ext = [(a.url, a.filename, False) for a in message.attachments]

        images = []
        attachments = []
        for attachment in ext:
            if is_image_url(attachment[0]):
                images.append(attachment)
            else:
                attachments.append(attachment)

        image_urls = re.findall(
            r"http[s]?:\/\/(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            message.content,
        )

        image_urls = [
            (is_image_url(url, convert_size=False), None, False)
            for url in image_urls
            if is_image_url(url, convert_size=False)
        ]
        images.extend(image_urls)

        def lottie_to_png(data):
            importer = l_importers.get("lottie")
            exporter = l_exporters.get("png")
            with io.BytesIO() as stream:
                stream.write(data)
                stream.seek(0)
                an = importer.process(stream)

            with io.BytesIO() as stream:
                exporter.process(an, stream)
                stream.seek(0)
                return stream.read()

        for i in message.stickers:
            if i.format in (
                discord.StickerFormatType.png,
                discord.StickerFormatType.apng,
                discord.StickerFormatType.gif,
            ):
                images.append(
                    (f"https://media.discordapp.net/stickers/{i.id}.{i.format.file_extension}", i.name, True)
                )
            elif i.format == discord.StickerFormatType.lottie:
                # save the json lottie representation
                try:
                    async with self.bot.session.get(i.url) as resp:
                        data = await resp.read()

                    # convert to a png
                    img_data = await self.bot.loop.run_in_executor(
                        None, functools.partial(lottie_to_png, data)
                    )
                    b64_data = base64.b64encode(img_data).decode()

                    # upload to imgur
                    async with self.bot.session.post(
                        "https://api.imgur.com/3/image",
                        headers={"Authorization": "Client-ID 50e96145ac5e085"},
                        data={"image": b64_data},
                    ) as resp:
                        result = await resp.json()
                        url = result["data"]["link"]

                except Exception:
                    traceback.print_exc()
                    images.append((None, i.name, True))
                else:
                    images.append((url, i.name, True))
            else:
                images.append((None, i.name, True))

        embedded_image = False

        prioritize_uploads = any(i[1] is not None for i in images)

        additional_images = []
        additional_count = 1

        for url, filename, is_sticker in images:
            if (
                not prioritize_uploads or ((url is None or is_image_url(url)) and filename)
            ) and not embedded_image:
                if url is not None:
                    embed.set_image(url=url)
                if filename:
                    if is_sticker:
                        if url is None:
                            description = f"{filename}: Unable to retrieve sticker image"
                        else:
                            description = f"[{filename}]({url})"
                        embed.add_field(name="Sticker", value=description)
                    else:
                        embed.add_field(name="Image", value=f"[{filename}]({url})")
                embedded_image = True
            else:
                if note:
                    color = self.bot.main_color
                elif from_mod:
                    color = self.bot.mod_color
                else:
                    color = self.bot.recipient_color

                img_embed = discord.Embed(color=color)

                if url is not None:
                    img_embed.set_image(url=url)
                    img_embed.url = url
                if filename is not None:
                    img_embed.title = filename
                img_embed.set_footer(text=f"Additional Image Upload ({additional_count})")
                img_embed.timestamp = message.created_at
                additional_images.append(destination.send(embed=img_embed))
                additional_count += 1

        file_upload_count = 1

        for url, filename, _ in attachments:
            embed.add_field(name=f"File upload ({file_upload_count})", value=f"[{filename}]({url})")
            file_upload_count += 1

        if from_mod:
            if note:
                # Notes use Discord blurple and special footer
                embed.colour = 0x5865F2
                if persistent_note:
                    embed.set_footer(text="Persistent Internal Note")
                else:
                    embed.set_footer(text="Internal Note")
            else:
                # Regular mod messages
                embed.colour = self.bot.mod_color
                # Anonymous reply sent in thread channel
                if anonymous and isinstance(destination, discord.TextChannel):
                    embed.set_footer(text="Anonymous Reply")
                # Normal messages
                elif not anonymous:
                    mod_tag = self.bot.config["mod_tag"]
                    if mod_tag is None:
                        mod_tag = str(get_top_role(message.author, self.bot.config["use_hoisted_top_role"]))
                    embed.set_footer(text=mod_tag)  # Normal messages
                else:
                    embed.set_footer(text=self.bot.config["anon_tag"])
        else:
            # Add forwarded message indicator in footer for mods
            footer_text = f"Message ID: {message.id}"
            if hasattr(message, "message_snapshots") and len(message.message_snapshots) > 0:
                footer_text += " • Forwarded"
            embed.set_footer(text=footer_text)
            embed.colour = self.bot.recipient_color

        if (from_mod or note) and not thread_creation:
            delete_message = not bool(message.attachments)
            if delete_message and destination == self.channel:
                try:
                    await message.delete()
                except Exception as e:
                    logger.warning("Cannot delete message: %s.", e)

        if (
            from_mod
            and self.bot.config["dm_disabled"] == DMDisabled.ALL_THREADS
            and destination != self.channel
        ):
            logger.info("Sending a message to %s when DM disabled is set.", self.recipient)

        # Best-effort typing: never block message delivery if typing fails
        try:
            await destination.typing()
        except discord.NotFound:
            logger.warning("Channel not found.")
            raise
        except (discord.Forbidden, discord.HTTPException, Exception) as e:
            logger.warning("Unable to send typing to %s: %s. Continuing without typing.", destination, e)

        if not from_mod and not note:
            mentions = await self.get_notifications()
        else:
            mentions = None

        if plain:
            if from_mod and not isinstance(destination, discord.TextChannel):
                # Plain to user
                with warnings.catch_warnings():
                    # Catch coroutines not awaited warning
                    warnings.simplefilter("ignore")
                    additional_images = []

                if embed.footer.text:
                    plain_message = f"**{embed.footer.text} "
                else:
                    plain_message = "**"
                plain_message += f"{embed.author.name}:** {embed.description}"
                files = []
                for i in message.attachments:
                    files.append(await i.to_file())

                msg = await destination.send(plain_message, files=files)
            else:
                # Plain to mods
                embed.set_footer(text="[PLAIN] " + embed.footer.text)
                msg = await destination.send(mentions, embed=embed)

        else:
            msg = await destination.send(mentions, embed=embed)

        if additional_images:
            self.ready = False
            await asyncio.gather(*additional_images)
            self.ready = True

        return msg

    async def get_notifications(self) -> str:
        key = str(self.id)

        mentions = []
        mentions.extend(self.bot.config["subscriptions"].get(key, []))

        if key in self.bot.config["notification_squad"]:
            mentions.extend(self.bot.config["notification_squad"][key])
            self.bot.config["notification_squad"].pop(key)
            self.bot.loop.create_task(self.bot.config.update())

        return " ".join(set(mentions))

    async def set_title(self, title: str) -> None:
        topic = f"Title: {title}\n"

        user_id = match_user_id(self.channel.topic)
        topic += f"User ID: {user_id}"

        if self._other_recipients:
            ids = ",".join(str(i.id) for i in self._other_recipients)
            topic += f"\nOther Recipients: {ids}"

        await self.channel.edit(topic=topic)

    async def _update_users_genesis(self):
        genesis_message = await self.get_genesis_message()
        embed = genesis_message.embeds[0]
        value = " ".join(x.mention for x in self._other_recipients)
        index = None
        for n, field in enumerate(embed.fields):
            if field.name == "Other Recipients":
                index = n
                break

        if index is None and value:
            embed.add_field(name="Other Recipients", value=value, inline=False)
        else:
            if value:
                embed.set_field_at(index, name="Other Recipients", value=value, inline=False)
            else:
                embed.remove_field(index)

        await genesis_message.edit(embed=embed)

    async def add_users(self, users: typing.List[typing.Union[discord.Member, discord.User]]) -> None:
        topic = ""
        title, _, _ = parse_channel_topic(self.channel.topic)
        if title is not None:
            topic += f"Title: {title}\n"

        topic += f"User ID: {self._id}"

        self._other_recipients += users
        self._other_recipients = list(set(self._other_recipients))

        ids = ",".join(str(i.id) for i in self._other_recipients)

        topic += f"\nOther Recipients: {ids}"

        await self.channel.edit(topic=topic)
        await self._update_users_genesis()

    async def remove_users(self, users: typing.List[typing.Union[discord.Member, discord.User]]) -> None:
        topic = ""
        title, user_id, _ = parse_channel_topic(self.channel.topic)
        if title is not None:
            topic += f"Title: {title}\n"

        topic += f"User ID: {user_id}"

        for u in users:
            self._other_recipients.remove(u)

        if self._other_recipients:
            ids = ",".join(str(i.id) for i in self._other_recipients)
            topic += f"\nOther Recipients: {ids}"

        await self.channel.edit(topic=topic)
        await self._update_users_genesis()


class ThreadManager:
    """Class that handles storing, finding and creating Modmail threads."""

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}
        self.closing = set()

    async def populate_cache(self) -> None:
        for channel in self.bot.modmail_guild.text_channels:
            await self.find(channel=channel)

    def __len__(self):
        return len(self.cache)

    def __iter__(self):
        return iter(self.cache.values())

    def __getitem__(self, item: str) -> Thread:
        return self.cache[item]

    async def find(
        self,
        *,
        recipient: typing.Union[discord.Member, discord.User] = None,
        channel: discord.TextChannel = None,
        recipient_id: int = None,
    ) -> typing.Optional[Thread]:
        """Finds a thread from cache or from discord channel topics."""
        if recipient is None and channel is not None and isinstance(channel, discord.TextChannel):
            if channel.id in self.closing:
                return None
            thread = await self._find_from_channel(channel)
            if thread is None:
                user_id, thread = next(
                    ((k, v) for k, v in self.cache.items() if v.channel == channel), (-1, None)
                )
                if thread is not None:
                    logger.debug("Found thread with tempered ID.")
                    await channel.edit(topic=f"User ID: {user_id}")
            return thread

        if recipient:
            recipient_id = recipient.id

        thread = self.cache.get(recipient_id)
        if thread is not None:
            try:
                await thread.wait_until_ready()
            except asyncio.CancelledError:
                logger.warning("Thread for %s cancelled.", recipient)
                return thread
            else:
                # If the thread is snoozed (channel is None), return it for restoration
                if thread.cancelled:
                    thread = None
        else:

            def check(topic):
                _, user_id, other_ids = parse_channel_topic(topic)
                return recipient_id == user_id or recipient_id in other_ids

            channel = discord.utils.find(
                lambda x: (check(x.topic)) if x.topic else False,
                self.bot.modmail_guild.text_channels,
            )

            if channel:
                thread = await Thread.from_channel(self, channel)
                if thread.recipient:
                    # only save if data is valid.
                    # also the recipient_id here could belong to other recipient,
                    # it would be wrong if we set it as the dict key,
                    # so we use the thread id instead
                    self.cache[thread.id] = thread
                thread.ready = True

        if thread and recipient_id not in [x.id for x in thread.recipients]:
            self.cache.pop(recipient_id)
            thread = None

        return thread

    async def _find_from_channel(self, channel):
        """
        Tries to find a thread from a channel channel topic,
        if channel topic doesnt exist for some reason, falls back to
        searching channel history for genesis embed and
        extracts user_id from that.
        """

        if not channel.topic:
            return None

        _, user_id, other_ids = parse_channel_topic(channel.topic)

        if user_id == -1:
            return None

        if user_id in self.cache:
            return self.cache[user_id]

        try:
            recipient = await self.bot.get_or_fetch_user(user_id)
        except discord.NotFound:
            recipient = None

        other_recipients = []
        for uid in other_ids:
            try:
                other_recipient = await self.bot.get_or_fetch_user(uid)
            except discord.NotFound:
                continue
            other_recipients.append(other_recipient)

        if recipient is None:
            thread = Thread(self, user_id, channel, other_recipients)
        else:
            self.cache[user_id] = thread = Thread(self, recipient, channel, other_recipients)
        thread.ready = True

        return thread

    async def create(
        self,
        recipient: typing.Union[discord.Member, discord.User],
        *,
        message: discord.Message = None,
        creator: typing.Union[discord.Member, discord.User] = None,
        category: discord.CategoryChannel = None,
        manual_trigger: bool = True,
    ) -> Thread:
        """Creates a Modmail thread"""

        # Minimum character check
        min_chars = self.bot.config.get("thread_min_characters")
        if min_chars is None:
            min_chars = 0
        try:
            min_chars = int(min_chars)
        except ValueError:
            min_chars = 0
        if min_chars > 0 and message is not None and message.content is not None:
            if len(message.content.strip()) < min_chars:
                embed = discord.Embed(
                    title=self.bot.config["thread_min_characters_title"],
                    description=self.bot.config["thread_min_characters_response"].replace(
                        "{min_characters}", str(min_chars)
                    ),
                    color=self.bot.error_color,
                )
                embed.set_footer(
                    text=self.bot.config["thread_min_characters_footer"].replace(
                        "{min_characters}", str(min_chars)
                    )
                )
                await message.channel.send(embed=embed)
                thread = Thread(self, recipient)
                thread.cancelled = True
                return thread

        # checks for existing thread in cache
        thread = self.cache.get(recipient.id)
        if thread:
            try:
                await thread.wait_until_ready()
            except asyncio.CancelledError:
                logger.warning("Thread for %s cancelled, abort creating.", recipient)
                return thread
            else:
                if thread.channel and self.bot.get_channel(thread.channel.id):
                    logger.warning("Found an existing thread for %s, abort creating.", recipient)
                    return thread
                logger.warning("Found an existing thread for %s, closing previous thread.", recipient)
                self.bot.loop.create_task(
                    thread.close(closer=self.bot.user, silent=True, delete_channel=False)
                )

        thread = Thread(self, recipient)

        self.cache[recipient.id] = thread

        if (message or not manual_trigger) and self.bot.config["confirm_thread_creation"]:
            if not manual_trigger:
                destination = recipient
            else:
                destination = message.channel
            view = ConfirmThreadCreationView()
            view.add_item(
                AcceptButton("accept-thread-creation", self.bot.config["confirm_thread_creation_accept"])
            )
            view.add_item(DenyButton("deny-thread-creation", self.bot.config["confirm_thread_creation_deny"]))
            confirm = await destination.send(
                embed=discord.Embed(
                    title=self.bot.config["confirm_thread_creation_title"],
                    description=self.bot.config["confirm_thread_response"],
                    color=self.bot.main_color,
                ),
                view=view,
            )
            await view.wait()
            if view.value is None:
                thread.cancelled = True
                self.bot.loop.create_task(
                    destination.send(
                        embed=discord.Embed(
                            title=self.bot.config["thread_cancelled"],
                            description="Timed out",
                            color=self.bot.error_color,
                        )
                    )
                )
                await confirm.edit(view=None)
            if view.value is False:
                thread.cancelled = True
                self.bot.loop.create_task(
                    destination.send(
                        embed=discord.Embed(
                            title=self.bot.config["thread_cancelled"], color=self.bot.error_color
                        )
                    )
                )
            if thread.cancelled:
                del self.cache[recipient.id]
                return thread

        self.bot.loop.create_task(thread.setup(creator=creator, category=category, initial_message=message))
        return thread

    async def find_or_create(self, recipient) -> Thread:
        return await self.find(recipient=recipient) or await self.create(recipient)
