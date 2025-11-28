import asyncio
import copy
import base64
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
from discord.ext import commands
from discord.ext.commands import MissingRequiredArgument, CommandError
from lottie.importers import importers as l_importers
from lottie.exporters import exporters as l_exporters

from core.models import DMDisabled, DummyMessage, PermissionLevel, getLogger
from core import checks
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
        self._dm_menu_msg_id = None
        self._dm_menu_channel_id = None
        # --- SNOOZE STATE ---
        self.snoozed = False  # True if thread is snoozed
        self.snooze_data = None  # Dict with channel/category/position/messages for restoration
        self.log_key = None  # Ensure log_key always exists
        # --- UNSNOOZE COMMAND QUEUE ---
        self._unsnoozing = False  # True while restore_from_snooze is running
        self._command_queue = []  # Queue of (ctx, command) tuples; close commands always last

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
            logger.warning("Waiting for thread setup timed out.")
        finally:
            if task in self.wait_tasks:
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
    def ready(self, flag: bool) -> None:
        """Set the ready state and dispatch thread_create when transitioning to ready.

        Some legacy code paths set thread.ready = True/False. This setter preserves that API by
        updating the internal event and emitting the creation event when entering the ready state.
        """
        if flag:
            if not self._ready_event.is_set():
                self._ready_event.set()
                try:
                    self.bot.dispatch("thread_create", self)
                except Exception as e:
                    logger.warning("Error dispatching thread_create: %s", e)
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
        Save channel/category/position/messages to DB, mark as snoozed.
        Behavior is configurable:
        - delete (default): delete the channel and store all data for full restore later
        - move: move channel to a configured snoozed category and hide it (keeps channel alive)
        """
        if self.snoozed:
            return False  # Already snoozed
        channel = self.channel
        if not isinstance(channel, discord.TextChannel):
            return False
        # If using move-based snooze, hard-cap snoozed category to 49 channels
        behavior_pre = (self.bot.config.get("snooze_behavior") or "delete").lower()
        if behavior_pre == "move":
            snoozed_cat_id = self.bot.config.get("snoozed_category_id")
            target_category = None
            if snoozed_cat_id:
                try:
                    target_category = self.bot.modmail_guild.get_channel(int(snoozed_cat_id))
                except Exception:
                    target_category = None
            if isinstance(target_category, discord.CategoryChannel):
                try:
                    if len(target_category.channels) >= 49:
                        logger.warning(
                            "Snoozed category (%s) is full (>=49 channels). Blocking snooze for thread %s.",
                            target_category.id,
                            self.id,
                        )
                        return False
                except Exception:
                    # If we cannot determine channel count, proceed; downstream will handle errors
                    pass
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
                    "author_name": (
                        getattr(m.embeds[0].author, "name", "").split(" (")[0]
                        if m.embeds and m.embeds[0].author and m.author == self.bot.user
                        else getattr(m.author, "name", None)
                        if m.author != self.bot.user
                        else None
                    ),
                    "author_avatar": (
                        getattr(m.embeds[0].author, "icon_url", None)
                        if m.embeds and m.embeds[0].author and m.author == self.bot.user
                        else m.author.display_avatar.url
                        if m.author != self.bot.user
                        else None
                    ),
                }
                async for m in channel.history(limit=None, oldest_first=True)
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

        behavior = behavior_pre
        if behavior == "move":
            # Move the channel to the snoozed category (if configured) and optionally apply a prefix
            snoozed_cat_id = self.bot.config.get("snoozed_category_id")
            target_category = None
            guild = self.bot.modmail_guild
            if snoozed_cat_id:
                try:
                    target_category = guild.get_channel(int(snoozed_cat_id))
                except Exception:
                    target_category = None
            # If no valid snooze category is configured, create one automatically
            if not isinstance(target_category, discord.CategoryChannel):
                try:
                    # By default, hide the snoozed category from everyone and allow only the bot to see it
                    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
                    bot_member = guild.me
                    if bot_member is not None:
                        overwrites[bot_member] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True,
                            manage_channels=True,
                            manage_messages=True,
                            attach_files=True,
                            embed_links=True,
                            add_reactions=True,
                        )

                    target_category = await guild.create_category(
                        name="Snoozed Threads",
                        overwrites=overwrites,
                        reason="Auto-created snoozed category for move-based snoozing",
                    )
                    # Persist the newly created category ID into config for future runs
                    try:
                        await self.bot.config.set("snoozed_category_id", target_category.id)
                        await self.bot.config.update()
                    except Exception:
                        logger.warning("Failed to persist snoozed_category_id after auto-creation.")
                except Exception as e:
                    logger.warning(
                        "Failed to auto-create snoozed category (%s). Falling back to current category.",
                        e,
                    )
                    target_category = channel.category
            try:
                # Move and sync permissions so the channel inherits the hidden snoozed-category perms
                await channel.edit(
                    category=target_category,
                    reason="Thread snoozed (moved)",
                    sync_permissions=True,
                )
                # Keep channel reference; just moved
                self._channel = channel
                # mark in snooze data that this was a move-based snooze
                self.snooze_data["moved"] = True
            except Exception as e:
                logger.warning(
                    "Failed to move channel to snoozed category: %s. Falling back to delete.",
                    e,
                )
                await channel.delete(reason="Thread snoozed by moderator (fallback delete)")
                self._channel = None
        else:
            # Delete channel
            await channel.delete(reason="Thread snoozed by moderator")
            self._channel = None
        return True

    async def restore_from_snooze(self):
        """
        Restore a snoozed thread.
        - If channel was deleted (delete behavior), recreate and replay messages.
        - If channel was moved (move behavior), move back to original category and position.
        Mark as not snoozed and clear snooze data.
        """
        # Prevent concurrent unsnooze operations
        if self._unsnoozing:
            logger.warning(f"Unsnooze already in progress for thread {self.id}, skipping duplicate call")
            return False

        # Mark that unsnooze is in progress
        self._unsnoozing = True

        if not self.snooze_data or not isinstance(self.snooze_data, dict):
            import logging

            logging.warning(
                f"[UNSNOOZE] Tried to restore thread {self.id} but snooze_data is None or not a dict."
            )
            self._unsnoozing = False
            return False

        # Cache some fields we need later (before we potentially clear snooze_data)
        snoozed_by = self.snooze_data.get("snoozed_by")
        snooze_command = self.snooze_data.get("snooze_command")

        guild = self.bot.modmail_guild
        behavior = (self.bot.config.get("snooze_behavior") or "delete").lower()

        # Determine original category; fall back to main_category_id if original missing
        orig_category = (
            guild.get_channel(self.snooze_data.get("category_id"))
            if self.snooze_data.get("category_id")
            else None
        )
        if not isinstance(orig_category, discord.CategoryChannel):
            main_cat_id = self.bot.config.get("main_category_id")
            orig_category = guild.get_channel(int(main_cat_id)) if main_cat_id else None

        # Default: assume we'll need to recreate
        channel: typing.Optional[discord.TextChannel] = None

        # If move-behavior and channel still exists, move it back and restore overwrites
        if behavior == "move" and isinstance(self.channel, discord.TextChannel):
            try:
                await self.channel.edit(
                    category=orig_category,
                    position=self.snooze_data.get("position", self.channel.position),
                    reason="Thread unsnoozed/restored",
                )
                # Restore original overwrites captured at snooze time
                try:
                    ow_map: dict = {}
                    for role_id, perm_values in self.snooze_data.get("overwrites", []):
                        target = guild.get_role(role_id) or guild.get_member(role_id)
                        if target is None:
                            continue
                        ow_map[target] = discord.PermissionOverwrite(**perm_values)
                    if ow_map:
                        await self.channel.edit(overwrites=ow_map, reason="Restore original overwrites")
                except Exception as e:
                    logger.warning("Failed to restore original overwrites on unsnooze: %s", e)

                channel = self.channel
            except Exception as e:
                logger.warning("Failed to move snoozed channel back, recreating: %s", e)
                channel = None

        # If we couldn't move back (or behavior=delete), recreate the channel
        if channel is None:
            try:
                ow_map: dict = {}
                for role_id, perm_values in self.snooze_data.get("overwrites", []):
                    target = guild.get_role(role_id) or guild.get_member(role_id)
                    if target is None:
                        continue
                    ow_map[target] = discord.PermissionOverwrite(**perm_values)

                channel = await guild.create_text_channel(
                    name=self.snooze_data.get("name") or f"thread-{self.id}",
                    category=orig_category,
                    # discord.py expects a dict for overwrites; use empty dict if none
                    overwrites=ow_map or {},
                    position=self.snooze_data.get("position"),
                    topic=self.snooze_data.get("topic"),
                    slowmode_delay=self.snooze_data.get("slowmode_delay") or 0,
                    nsfw=bool(self.snooze_data.get("nsfw")),
                    reason="Thread unsnoozed/restored (recreated)",
                )
                self._channel = channel
            except Exception:
                logger.error("Failed to recreate thread channel during unsnooze.", exc_info=True)
                return False

        # Helper to safely send to thread channel, recreating once if deleted
        async def _safe_send_to_channel(*, content=None, embeds=None, allowed_mentions=None):
            nonlocal channel
            try:
                return await channel.send(content=content, embeds=embeds, allowed_mentions=allowed_mentions)
            except discord.NotFound:
                # Channel was deleted between restore and send; try to recreate once
                try:
                    ow_map: dict = {}
                    for role_id, perm_values in self.snooze_data.get("overwrites", []) or []:
                        target = guild.get_role(role_id) or guild.get_member(role_id)
                        if target is None:
                            continue
                        ow_map[target] = discord.PermissionOverwrite(**perm_values)
                    channel = await guild.create_text_channel(
                        name=(self.snooze_data.get("name") or f"thread-{self.id}"),
                        category=orig_category,
                        # discord.py expects a dict for overwrites; use empty dict if none
                        overwrites=ow_map or {},
                        position=self.snooze_data.get("position"),
                        topic=self.snooze_data.get("topic"),
                        slowmode_delay=self.snooze_data.get("slowmode_delay") or 0,
                        nsfw=bool(self.snooze_data.get("nsfw")),
                        reason="Thread unsnoozed/restored (recreated after NotFound)",
                    )
                    self._channel = channel
                    return await channel.send(
                        content=content,
                        embeds=embeds,
                        allowed_mentions=allowed_mentions,
                    )
                except Exception:
                    logger.error(
                        "Failed to recreate channel during unsnooze send.",
                        exc_info=True,
                    )
                    return None

        # Ensure genesis message exists; always present after unsnooze
        genesis_already_sent = False

        async def _ensure_genesis(force: bool = False):
            nonlocal genesis_already_sent
            try:
                existing = await self.get_genesis_message()
            except Exception:
                existing = None
            if existing is None or force:
                # Build log_url and log_count best-effort
                prefix = (self.bot.config.get("log_url_prefix") or "").strip("/")
                if prefix == "NONE":
                    prefix = ""
                key = self.snooze_data.get("log_key") or self.log_key
                log_url = (
                    f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{key}"
                    if key
                    else None
                )
                log_count = None
                try:
                    logs = await self.bot.api.get_user_logs(self.id)
                    log_count = sum(1 for log in logs if not log.get("open"))
                except Exception:
                    log_count = None
                # Resolve recipient object
                user = self.recipient
                if user is None:
                    try:
                        user = await self.bot.get_or_fetch_user(self.id)
                    except Exception:
                        user = SimpleNamespace(
                            id=self.id,
                            mention=f"<@{self.id}>",
                            created_at=datetime.now(timezone.utc),
                        )
                try:
                    info_embed = self._format_info_embed(user, log_url, log_count, self.bot.main_color)
                    msg = await channel.send(embed=info_embed)
                    try:
                        await msg.pin()
                    except Exception as e:
                        logger.warning("Failed to pin genesis message during unsnooze: %s", e)
                    self._genesis_message = msg
                    genesis_already_sent = True
                except Exception:
                    logger.warning("Failed to send genesis message during unsnooze.", exc_info=True)

        # If we recreated the channel, force-send genesis; if moved back, ensure it's present
        try:
            if behavior == "move" and isinstance(channel, discord.TextChannel):
                await _ensure_genesis(force=False)
            else:
                await _ensure_genesis(force=True)
        except Exception:
            logger.debug("Genesis ensure step encountered an error.")

        # Strictly restore the log_key from snooze_data (never create a new one)
        self.log_key = self.snooze_data.get("log_key")

        # Replay messages only if we re-created the channel (delete behavior or move fallback)
        if behavior != "move" or (behavior == "move" and not self.snooze_data.get("moved", False)):
            # Get history limit from config (0 or None = show all)
            history_limit = self.bot.config.get("unsnooze_history_limit")
            all_messages = self.snooze_data.get("messages", [])

            # Separate genesis, notes, and regular messages
            genesis_msg = None
            notes = []
            regular_messages = []

            for msg in all_messages:
                msg_type = msg.get("type")
                # Check if it's the genesis message (has Roles field)
                if msg.get("embeds"):
                    for embed_dict in msg.get("embeds", []):
                        if embed_dict.get("fields"):
                            for field in embed_dict.get("fields", []):
                                if field.get("name") == "Roles":
                                    genesis_msg = msg
                                    break
                            if genesis_msg:
                                break
                # Check if it's a note
                if msg_type == "mod_only":
                    notes.append(msg)
                elif genesis_msg != msg:
                    regular_messages.append(msg)

            # Apply limit if set
            limited = False
            if history_limit:
                try:
                    history_limit = int(history_limit)
                    if history_limit > 0 and len(regular_messages) > history_limit:
                        regular_messages = regular_messages[-history_limit:]
                        limited = True
                except (ValueError, TypeError):
                    pass

            # Replay genesis first (only if we didn't already create it above)
            if genesis_msg and not genesis_already_sent:
                msg = genesis_msg
                try:
                    author = self.bot.get_user(msg["author_id"]) or await self.bot.get_or_fetch_user(
                        msg["author_id"]
                    )
                except discord.NotFound:
                    author = None
                embeds = [discord.Embed.from_dict(e) for e in msg.get("embeds", []) if e]
                if embeds:
                    await _safe_send_to_channel(
                        embeds=embeds, allowed_mentions=discord.AllowedMentions.none()
                    )

            # Send history limit notification after genesis
            if limited:
                prefix = self.bot.config["log_url_prefix"].strip("/")
                if prefix == "NONE":
                    prefix = ""
                log_url = (
                    f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{self.log_key}"
                    if self.log_key
                    else None
                )

                limit_embed = discord.Embed(
                    color=0xFFA500,
                    title="⚠️ History Limited",
                    description=f"Only showing the last **{history_limit}** messages due to the `unsnooze_history_limit` setting.",
                )
                if log_url:
                    limit_embed.description += f"\n\n[View full history in logs]({log_url})"
                await _safe_send_to_channel(
                    embeds=[limit_embed],
                    allowed_mentions=discord.AllowedMentions.none(),
                )

            # Build list of remaining messages to show
            messages_to_show = []
            messages_to_show.extend(notes)
            messages_to_show.extend(regular_messages)

            for msg in messages_to_show:
                try:
                    author = self.bot.get_user(msg["author_id"]) or await self.bot.get_or_fetch_user(
                        msg["author_id"]
                    )
                except discord.NotFound:
                    author = None

                content = msg.get("content")
                embeds = [discord.Embed.from_dict(e) for e in msg.get("embeds", []) if e]
                attachments = msg.get("attachments", [])

                # Only send if there is something to send
                if not content and not embeds and not attachments:
                    continue

                author_is_mod = msg["author_id"] not in [r.id for r in self.recipients]
                if author_is_mod:
                    # Prefer stored author_name/avatar
                    username = (
                        msg.get("author_name")
                        or (getattr(author, "name", None) if author else None)
                        or "Unknown"
                    )
                    user_id = msg.get("author_id")
                    if embeds:
                        # Ensure embeds show author details
                        embeds[0].set_author(
                            name=f"{username} ({user_id})",
                            icon_url=msg.get("author_avatar")
                            or (
                                author.display_avatar.url
                                if author and hasattr(author, "display_avatar")
                                else None
                            ),
                        )
                        # If there were attachment URLs, include them as a field so mods can access them
                        if attachments:
                            try:
                                embeds[0].add_field(
                                    name="Attachments",
                                    value="\n".join(attachments),
                                    inline=False,
                                )
                            except Exception as e:
                                logger.info(
                                    "Failed to add attachments field while replaying unsnoozed messages: %s",
                                    e,
                                )
                        await _safe_send_to_channel(
                            embeds=embeds,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    else:
                        # Plain-text path (no embeds): prefix with username and user id
                        header = f"**{username} ({user_id})**"
                        body = content or ""
                        if attachments and not body:
                            # no content; include attachment URLs on new lines
                            body = "\n".join(attachments)
                        formatted = f"{header}: {body}" if body else header
                        await _safe_send_to_channel(
                            content=formatted,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                else:
                    # Recipient message: include attachment URLs if content is empty
                    # When no embeds, prefix plain text with username and user id
                    username = (
                        msg.get("author_name")
                        or (getattr(author, "name", None) if author else None)
                        or "Unknown"
                    )
                    user_id = msg.get("author_id")
                    if embeds:
                        await _safe_send_to_channel(
                            content=None,
                            embeds=embeds or None,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    else:
                        header = f"**{username} ({user_id})**"
                        body = content or ""
                        if attachments and not body:
                            body = "\n".join(attachments)
                        formatted = f"{header}: {body}" if body else header
                        await _safe_send_to_channel(
                            content=formatted,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
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
            await _safe_send_to_channel(content=notify_text, allowed_mentions=discord.AllowedMentions.none())
        else:
            # Extract channel ID from mention format <#123> or use raw ID
            channel_id = str(notify_channel).strip("<#>")
            ch = self.bot.get_channel(int(channel_id))
            if ch:
                await ch.send(
                    f"⏰ Thread for user <@{self.id}> has been unsnoozed and restored in {channel.mention}",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        # Show who ran the snooze command and the command used
        # Use snooze_data_for_notify to avoid accessing self.snooze_data after it is set to None
        snoozed_by = snooze_data_for_notify.get("snoozed_by") if snooze_data_for_notify else None
        snooze_command = snooze_data_for_notify.get("snooze_command") if snooze_data_for_notify else None
        if snoozed_by or snooze_command:
            info = f"Snoozed by: {snoozed_by or 'Unknown'} | Command: {snooze_command or '?snooze'}"
            await channel.send(info, allowed_mentions=discord.AllowedMentions.none())

        # Ensure channel is set before processing commands
        self._channel = channel

        # Mark unsnooze as complete
        self._unsnoozing = False

        # Process queued commands
        await self._process_command_queue()

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

        # If thread menu is enabled and this setup call is marked as deferred genesis (initial_message carries flag),
        # then we may have already created the channel earlier. Only create if channel missing.
        if self._channel is None:
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
            else:
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
                # Option selection logging (if a thread-creation menu option was chosen prior to creation)
                if getattr(self, "_selected_thread_creation_menu_option", None) and self.bot.config.get(
                    "thread_creation_menu_selection_log"
                ):
                    opt = self._selected_thread_creation_menu_option
                    try:
                        log_txt = f"Selected menu option: {opt.get('label')} ({opt.get('type')})"
                        if opt.get("type") == "command":
                            log_txt += f" -> {opt.get('callback')}"
                        await channel.send(embed=discord.Embed(description=log_txt, color=self.bot.mod_color))
                    except Exception:
                        logger.warning(
                            "Failed logging thread-creation menu selection",
                            exc_info=True,
                        )
            except Exception:
                logger.error("Failed unexpectedly:", exc_info=True)

        async def send_recipient_genesis_message():
            # Once thread is ready, tell the recipient (don't send if using contact on others)
            # Allow disabling the DM receipt embed via config
            if not self.bot.config.get("thread_creation_send_dm_embed"):
                # If self-closable is enabled, add the close reaction to the user's
                # original message instead so functionality is preserved without an embed.
                try:
                    recipient_thread_close = self.bot.config.get("recipient_thread_close")
                    if recipient_thread_close and initial_message is not None:
                        close_emoji = self.bot.config["close_emoji"]
                        close_emoji = await self.bot.convert_emoji(close_emoji)
                        await self.bot.add_reaction(initial_message, close_emoji)
                except Exception as e:
                    logger.info("Failed to add self-close reaction to initial message: %s", e)
                return

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
                text=footer,
                icon_url=self.bot.get_guild_icon(guild=self.bot.guild, size=128),
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
        # Proactively disable any DM thread-creation menu so users can't keep interacting
        # with the menu after the thread is closed.
        try:
            await self._disable_dm_creation_menu()
        except Exception:
            # Non-fatal; continue closing even if we can't edit the DM menu
            pass
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
            # Only create a URL button if we actually have a valid log_url
            view = None
            if self.bot.config.get("show_log_url_button") and log_url:
                view = discord.ui.View()
                view.add_item(discord.ui.Button(label="Log link", url=log_url, style=discord.ButtonStyle.url))
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
            message,
            closer=closer,
            loglink=log_url,
            logkey=log_data["key"] if log_data else None,
        )

        embed.description = message
        footer = self.bot.config["thread_close_footer"]
        embed.set_footer(
            text=footer,
            icon_url=self.bot.get_guild_icon(guild=self.bot.guild, size=128),
        )

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

    async def _disable_dm_creation_menu(self) -> None:
        """Best-effort removal of the interactive DM menu view sent during thread creation."""
        if not self._dm_menu_msg_id:
            return
        # We only ever send the menu to the main recipient
        user = self.recipient
        if not isinstance(user, (discord.User, discord.Member)):
            return
        # Ensure we have a DM channel
        dm: typing.Optional[discord.DMChannel] = getattr(user, "dm_channel", None)
        if dm is None:
            try:
                dm = await user.create_dm()
            except Exception as e:
                logger.info("Failed creating DM channel for menu disable: %s", e)
                dm = None
        if not isinstance(dm, discord.DMChannel):
            return
        # If we stored the channel id and it differs, but it's still a DM, continue anyway
        try:
            msg = await dm.fetch_message(self._dm_menu_msg_id)
        except (discord.NotFound, discord.Forbidden):
            return
        except Exception:
            return
        try:
            closed_text = "This thread has been closed. Send a new message to start a new thread."  # Grammar-friendly guidance
            closed_embed = discord.Embed(description=closed_text)
            await msg.edit(content=None, embed=closed_embed, view=None)
        except Exception as e:
            # Fallback: at least remove interaction so menu cannot be used
            logger.warning("Failed editing DM menu message on close: %s", e)
            try:
                await msg.edit(view=None)
            except Exception as inner_e:
                logger.debug("Failed removing view from DM menu message: %s", inner_e)

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

        await self.close(
            closer=self.bot.user,
            after=int(seconds),
            message=close_message,
            auto_close=True,
        )

    async def find_linked_messages(
        self,
        message_id: typing.Optional[int] = None,
        either_direction: bool = False,
        message1: discord.Message = None,
        note: bool = True,
    ) -> typing.Tuple[discord.Message, typing.List[typing.Optional[discord.Message]]]:
        if message1 is not None:
            if note:
                # For notes, don't require author.url; rely on footer/author.name markers
                if not message1.embeds or message1.author != self.bot.user:
                    logger.warning(
                        f"Malformed note for deletion: embeds={bool(message1.embeds)}, author={message1.author}"
                    )
                    raise ValueError("Malformed note message.")
            else:
                if (
                    not message1.embeds
                    or not message1.embeds[0].author.url
                    or message1.author != self.bot.user
                ):
                    logger.debug(
                        f"Malformed thread message for deletion: embeds={bool(message1.embeds)}, author_url={getattr(message1.embeds[0], 'author', None) and message1.embeds[0].author.url}, author={message1.author}"
                    )
                    # Keep original error string to avoid extra failure embeds in on_message_delete
                    raise ValueError("Malformed thread message.")

        elif message_id is not None:
            try:
                message1 = await self.channel.fetch_message(message_id)
            except discord.NotFound:
                logger.warning(f"Message ID {message_id} not found in channel history.")
                raise ValueError("Thread message not found.")

            if note:
                # Try to treat as note/persistent note first
                if message1.embeds and message1.author == self.bot.user:
                    footer_text = (message1.embeds[0].footer and message1.embeds[0].footer.text) or ""
                    author_name = getattr(message1.embeds[0].author, "name", "") or ""
                    is_note = (
                        "internal note" in footer_text.lower()
                        or "persistent internal note" in footer_text.lower()
                        or author_name.startswith("📝 Note")
                        or author_name.startswith("📝 Persistent Note")
                    )
                    if is_note:
                        # Notes have no linked DM counterpart; keep None sentinel
                        return message1, None
                # else: fall through to relay checks below

            # Non-note path (regular relayed messages): require author.url and colors
            if not (
                message1.embeds
                and message1.embeds[0].author.url
                and message1.embeds[0].color
                and message1.author == self.bot.user
            ):
                logger.warning(
                    f"Message {message_id} is not a valid modmail relay message. embeds={bool(message1.embeds)}, author_url={getattr(message1.embeds[0], 'author', None) and message1.embeds[0].author.url}, color={getattr(message1.embeds[0], 'color', None)}, author={message1.author}"
                )
                raise ValueError("Thread message not found.")

            if message1.embeds[0].footer and "Internal Message" in message1.embeds[0].footer.text:
                if not note:
                    logger.warning(
                        f"Message {message_id} is an internal message, but note deletion not requested."
                    )
                    raise ValueError("Thread message is an internal message, not a note.")
                # Internal bot-only message treated similarly; keep None sentinel
                return message1, None

            if message1.embeds[0].color.value != self.bot.mod_color and not (
                either_direction and message1.embeds[0].color.value == self.bot.recipient_color
            ):
                logger.warning("Message color does not match mod/recipient colors.")
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

        tasks = [
            self.bot.api.edit_message(message1.id, message),
            message1.edit(embed=embed1),
        ]
        if message1.embeds[0].footer and "Persistent Internal Note" in message1.embeds[0].footer.text:
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
        # Always delete the primary thread message
        tasks += [message1.delete()]

        for m2 in message2:
            if m2 is not None:
                tasks += [m2.delete()]

        if message1.embeds[0].footer and "Persistent Internal Note" in message1.embeds[0].footer.text:
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
        self,
        message: discord.Message,
        content: typing.Optional[str] = None,
        anonymous: bool = False,
        plain: bool = False,
    ) -> typing.Tuple[typing.List[discord.Message], discord.Message]:
        """Send a moderator reply to the thread.

        Parameters
        ----------
        message: discord.Message
            The invoking command message (contains attachments, stickers, etc.).
        content: Optional[str]
            Raw reply text to send instead of using ``message.content``. This avoids
            mutating ``message.content`` upstream and lets command handlers pass the
            processed text directly.
        anonymous: bool
            Whether to mask the moderator identity in the recipient DM.
        plain: bool
            Whether to send a plain (non-embed) message to the recipient.

        Returns
        -------
        Tuple[List[discord.Message], discord.Message]
            A list of messages sent to recipients and the copy sent in the thread channel.
        """
        # If this thread was snoozed using move-behavior, unsnooze automatically when a mod replies
        try:
            behavior = (self.bot.config.get("snooze_behavior") or "delete").lower()
        except Exception:
            behavior = "delete"
        if self.snoozed and behavior == "move":
            # Ensure we have snooze_data to restore location
            if not self.snooze_data:
                try:
                    log_entry = await self.bot.api.logs.find_one(
                        {"recipient.id": str(self.id), "snoozed": True}
                    )
                    if log_entry:
                        self.snooze_data = log_entry.get("snooze_data")
                except Exception as e:
                    logger.info(
                        "Failed to fetch snooze_data before auto-unsnooze on reply: %s",
                        e,
                    )
            try:
                await self.restore_from_snooze()
            except Exception as e:
                logger.warning("Auto-unsnooze on reply failed: %s", e)

        if not message.content and not message.attachments and not message.stickers:
            raise MissingRequiredArgument(DummyParam("msg"))
        for guild in self.bot.guilds:
            try:
                if await self.bot.get_or_fetch_member(guild, self.id):
                    break
            except discord.NotFound:
                logger.info(
                    "Recipient not found in guild %s when checking mutual servers.",
                    guild.id if hasattr(guild, "id") else guild,
                )
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
                    content_override=content,
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
            try:
                msg = await self.send(
                    message,
                    destination=self.channel,
                    from_mod=True,
                    anonymous=anonymous,
                    plain=plain,
                    content_override=content,
                )
            except discord.NotFound:
                logger.warning(
                    "Thread channel not found while replying; skipping thread-channel copy of the message."
                )
                msg = None

            if msg is not None:
                tasks.append(
                    self.bot.api.append_log(
                        message,
                        message_id=msg.id,
                        channel_id=self.channel.id,
                        type_="anonymous" if anonymous else "thread_message",
                    )
                )
            else:
                logger.warning(
                    "Thread channel message failed to send; skipping append_log. Channel may be missing."
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
        *,
        content_override: typing.Optional[str] = None,
    ) -> None:
        """Low-level send routine used by reply/note logic.

        Parameters
        ----------
        message: discord.Message
            The command invocation message (source of attachments/stickers).
        destination: Channel/User/Member
            Where to send the constructed message/embed.
        from_mod: bool
            Indicates this is a staff reply (affects author display + logging).
        note: bool
            Internal note style instead of a regular reply.
        anonymous / plain / persistent_note / thread_creation: Various flags controlling style.
        content_override: Optional[str]
            Explicit text to use instead of ``message.content``. Provided by refactored
            reply commands to avoid mutating the original message object.
        """
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
        # Initial typing was attempted here previously, but returning on NotFound caused callers to
        # receive None and crash when accessing attributes on the message. We rely on the
        # snooze-aware typing block below to handle typing and NotFound cases robustly.

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
                content = (content_override if content_override is not None else message.content) or ""

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
                    name = "Anonymous"
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
                # If this message originated from a thread-creation menu command callback
                # (user selected an option whose type is command), we force the author
                # display to be the bot to avoid showing the user as a replying moderator.
                if getattr(message, "_menu_invoked", False):
                    name = str(self.bot.user)
                    avatar_url = getattr(self.bot.user.display_avatar, "url", system_avatar_url)
                else:
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
                    (
                        f"https://media.discordapp.net/stickers/{i.id}.{i.format.file_extension}",
                        i.name,
                        True,
                    )
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
                    # Use configured mod_tag if provided; otherwise fallback to
                    # the author's top role when available, or their display name.
                    mod_tag = self.bot.config["mod_tag"]
                    if mod_tag is None:
                        if hasattr(message.author, "roles"):
                            try:
                                mod_tag = str(
                                    get_top_role(
                                        message.author,
                                        self.bot.config["use_hoisted_top_role"],
                                    )  # type: ignore[arg-type]
                                )
                            except Exception:
                                # As a safe fallback, prefer a stable display string
                                mod_tag = getattr(message.author, "display_name", str(message.author))
                        else:
                            mod_tag = getattr(message.author, "display_name", str(message.author))
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
            # Only delete the source command message when it's in a guild text
            # channel; attempting to delete a DM message can raise 50003.
            if (
                delete_message
                and destination == self.channel
                and hasattr(message, "channel")
                and isinstance(message.channel, discord.TextChannel)
            ):
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

        # Best-effort typing with snooze-aware retry: if channel was deleted during snooze, restore and retry once
        restored = False
        try:
            await destination.typing()
        except discord.NotFound:
            # Unknown Channel: if snoozed or we have snooze data, attempt to restore and retry once
            if isinstance(destination, discord.TextChannel) and (self.snoozed or self.snooze_data):
                logger.info("Thread channel missing while typing; attempting restore from snooze.")
                try:
                    await self.restore_from_snooze()
                    destination = self.channel or destination
                    restored = True
                    await destination.typing()
                except Exception as e:
                    logger.warning("Restore/typing retry failed: %s", e)
                    raise
            else:
                logger.warning("Channel not found.")
                raise
        except (discord.Forbidden, discord.HTTPException, Exception) as e:
            logger.warning(
                "Unable to send typing to %s: %s. Continuing without typing.",
                destination,
                e,
            )

        if not from_mod and not note:
            mentions = await self.get_notifications()
        else:
            mentions = None

        if plain:
            if from_mod and not isinstance(destination, discord.TextChannel):
                # Plain to user (DM)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    additional_images = []

                prefix = f"**{embed.footer.text} " if embed.footer and embed.footer.text else "**"
                body = embed.description or ""
                plain_message = f"{prefix}{embed.author.name}:** {body}"

                files = []
                for att in message.attachments:
                    try:
                        files.append(await att.to_file())
                    except Exception:
                        logger.warning("Failed to attach file in plain DM.", exc_info=True)

                msg = await destination.send(plain_message, files=files or None)
            else:
                # Plain to mods
                footer_text = embed.footer.text if embed.footer else ""
                embed.set_footer(text=f"[PLAIN] {footer_text}".strip())
                msg = await destination.send(mentions, embed=embed)

        else:
            try:
                msg = await destination.send(mentions, embed=embed)
            except discord.NotFound:
                if (
                    isinstance(destination, discord.TextChannel)
                    and (self.snoozed or self.snooze_data)
                    and not restored
                ):
                    logger.info("Thread channel missing while sending; attempting restore and resend.")
                    await self.restore_from_snooze()
                    destination = self.channel or destination
                    msg = await destination.send(mentions, embed=embed)
                else:
                    logger.warning("Channel not found during send.")
                    raise

        if additional_images:
            self.ready = False
            await asyncio.gather(*additional_images)
            self.ready = True

        return msg

    async def get_notifications(self) -> str:
        key = str(self.id)
        mentions: typing.List[str] = []
        subs = self.bot.config["subscriptions"].get(key, [])
        mentions.extend(subs)
        one_time = self.bot.config["notification_squad"].get(key, [])
        mentions.extend(one_time)

        if one_time:
            self.bot.config["notification_squad"].pop(key, None)
            self.bot.loop.create_task(self.bot.config.update())

        if not mentions:
            return ""
        return " ".join(list(dict.fromkeys(mentions)))

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

    async def queue_command(self, ctx, command) -> bool:
        """
        Queue a command to be executed after unsnooze completes.
        Close commands are automatically moved to the end of the queue.
        Returns True if command was queued, False if it should execute immediately.
        """
        if self._unsnoozing:
            command_name = command.qualified_name if command else ""

            # If it's a close command, always add to end
            if command_name == "close":
                self._command_queue.append((ctx, command))
            else:
                # For non-close commands, insert before any close commands
                close_index = None
                for i, (_, cmd) in enumerate(self._command_queue):
                    if cmd and cmd.qualified_name == "close":
                        close_index = i
                        break

                if close_index is not None:
                    self._command_queue.insert(close_index, (ctx, command))
                else:
                    self._command_queue.append((ctx, command))

            return True
        return False

    async def _process_command_queue(self) -> None:
        """
        Process all queued commands after unsnooze completes.
        Close commands are always last, so processing stops naturally after close.
        """
        if not self._command_queue:
            return

        logger.info(f"Processing {len(self._command_queue)} queued commands for thread {self.id}")

        # Process commands in order
        while self._command_queue:
            ctx, command = self._command_queue.pop(0)
            try:
                command_name = command.qualified_name if command else ""
                await self.bot.invoke(ctx)

                # If close command was executed, stop (it's always last anyway)
                if command_name == "close":
                    logger.info("Close command executed, queue processing complete")
                    break

            except Exception as e:
                logger.error(f"Error processing queued command: {e}", exc_info=True)


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
                    ((k, v) for k, v in self.cache.items() if v.channel == channel),
                    (-1, None),
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
                # Improve logging: include username and user ID when possible
                try:
                    if recipient is not None:
                        label = f"{recipient} ({recipient.id})"
                    elif recipient_id is not None:
                        user = await self.bot.get_or_fetch_user(recipient_id)
                        label = f"{user} ({recipient_id})" if user else f"User ({recipient_id})"
                    else:
                        label = "Unknown User"
                except Exception:
                    label = f"User ({recipient_id})" if recipient_id is not None else "Unknown User"
                logger.warning("Thread for %s cancelled.", label)
                return thread
            else:
                # If the thread is snoozed (channel is None), return it for restoration
                if thread.cancelled:
                    thread = None
                else:
                    # If the cached thread points to a deleted channel, treat as non-existent
                    try:
                        ch = getattr(thread, "channel", None)
                        if (
                            ch
                            and isinstance(ch, discord.TextChannel)
                            and self.bot.get_channel(getattr(ch, "id", None)) is None
                        ):
                            logger.info(
                                "Cached thread for %s references a deleted channel. Dropping stale cache entry.",
                                recipient_id,
                            )
                            self.cache.pop(thread.id, None)
                            thread = None
                    except Exception:
                        # If any attribute access fails, be safe and drop it.
                        self.cache.pop(getattr(thread, "id", None), None)
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
                # Improve logging to include username and ID
                try:
                    label = f"{recipient} ({recipient.id})"
                except Exception:
                    label = f"User ({getattr(recipient, 'id', 'unknown')})"
                logger.warning("Thread for %s cancelled, abort creating.", label)
                return thread
            else:
                if thread.channel and self.bot.get_channel(thread.channel.id):
                    logger.warning("Found an existing thread for %s, abort creating.", recipient)
                    return thread
                logger.warning(
                    "Found an existing thread for %s, closing previous thread.",
                    recipient,
                )
                self.bot.loop.create_task(
                    thread.close(closer=self.bot.user, silent=True, delete_channel=False)
                )

        thread = Thread(self, recipient)

        self.cache[recipient.id] = thread

        # Determine if the advanced thread-creation menu is enabled; if so and the user
        # initiated via DM, we defer confirmation until AFTER the user selects an option.
        adv_menu_enabled = self.bot.config.get("thread_creation_menu_enabled") and bool(
            self.bot.config.get("thread_creation_menu_options")
        )
        user_initiated_dm = (creator is None or creator == recipient) and manual_trigger

        if (
            (message or not manual_trigger)
            and self.bot.config["confirm_thread_creation"]
            and not (adv_menu_enabled and user_initiated_dm)
        ):
            if not manual_trigger:
                destination = recipient
            else:
                destination = message.channel
            view = ConfirmThreadCreationView()
            view.add_item(
                AcceptButton(
                    "accept-thread-creation",
                    self.bot.config["confirm_thread_creation_accept"],
                )
            )
            view.add_item(
                DenyButton(
                    "deny-thread-creation",
                    self.bot.config["confirm_thread_creation_deny"],
                )
            )
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
                            title=self.bot.config["thread_cancelled"],
                            color=self.bot.error_color,
                        )
                    )
                )
            if thread.cancelled:
                del self.cache[recipient.id]
                return thread

        # --- THREAD-CREATION MENU (deferred or precreate channel creation) ---
        adv_enabled = self.bot.config.get("thread_creation_menu_enabled") and bool(
            self.bot.config.get("thread_creation_menu_options")
        )
        user_initiated = (creator is None or creator == recipient) and manual_trigger
        precreate = (
            adv_enabled
            and user_initiated
            and bool(self.bot.config.get("thread_creation_menu_precreate_channel"))
        )
        if adv_enabled and user_initiated and not precreate:
            # Send menu prompt FIRST, wait for selection, then create channel.
            # Build dummy message for menu DM
            try:
                embed_text = self.bot.config.get("thread_creation_menu_embed_text")
                placeholder = self.bot.config.get("thread_creation_menu_dropdown_placeholder")
                timeout = int(self.bot.config.get("thread_creation_menu_timeout") or 20)
            except Exception:
                embed_text = "Please select an option."
                placeholder = "Select an option to contact the staff team."
                timeout = 20

            options = self.bot.config.get("thread_creation_menu_options") or {}
            submenus = self.bot.config.get("thread_creation_menu_submenus") or {}

            # Minimal inline view implementation (avoid importing plugin code)

            thread.ready = False  # not ready yet

            class _ThreadCreationMenuSelect(discord.ui.Select):
                def __init__(self, outer_thread: Thread):
                    self.outer_thread = outer_thread
                    opts = [
                        discord.SelectOption(
                            label=o["label"],
                            description=o["description"],
                            emoji=o["emoji"],
                        )
                        for o in options.values()
                    ]
                    super().__init__(
                        placeholder=placeholder,
                        min_values=1,
                        max_values=1,
                        options=opts,
                    )

                async def callback(self, interaction: discord.Interaction):
                    await interaction.response.defer(ephemeral=False)
                    # If the thread was snoozed before the user selected an option,
                    # restore it first so channel creation/setup & message relay work.
                    try:
                        if self.outer_thread.snoozed:
                            await self.outer_thread.restore_from_snooze()
                    except Exception:
                        logger.warning("Failed unsnoozing thread prior to menu selection; continuing.")
                    chosen_label = self.values[0]
                    # Resolve option key
                    key = chosen_label.lower().replace(" ", "_")
                    selected = options.get(key)
                    self.outer_thread._selected_thread_creation_menu_option = selected
                    # Reflect the selection in the original DM by editing the embed/body
                    try:
                        msg = getattr(interaction, "message", None)
                        if msg is None and self.view and hasattr(self.view, "message"):
                            msg = self.view.message
                        if msg is not None:
                            # Replace entire embed so only the selection line remains
                            try:
                                base_color = (msg.embeds[0].color if msg.embeds else None) or getattr(
                                    self.outer_thread.bot, "mod_color", None
                                )
                            except Exception:
                                base_color = getattr(self.outer_thread.bot, "mod_color", None)
                            selection_embed = (
                                discord.Embed(
                                    description=f"You selected: {chosen_label}",
                                    color=base_color,
                                )
                                if base_color is not None
                                else discord.Embed(description=f"You selected: {chosen_label}")
                            )
                            await msg.edit(content=None, embed=selection_embed, view=None)
                        else:
                            try:
                                await interaction.edit_original_response(
                                    content=f"You selected: {chosen_label}", view=None
                                )
                            except Exception as e:
                                # Fallback: best-effort remove the view at least
                                logger.info(
                                    "Primary edit_original_response failed; trying to remove view only: %s",
                                    e,
                                )
                                await interaction.edit_original_response(view=None)
                    except Exception as e:
                        # Ensure the menu is removed even if content edit failed
                        logger.warning("Failed to update selection message: %s", e)
                        try:
                            await interaction.edit_original_response(view=None)
                        except Exception as inner_e:
                            logger.debug(
                                "Failed to remove view after selection failure: %s",
                                inner_e,
                            )
                    # Stop the view to end the interaction lifecycle
                    if self.view:
                        try:
                            self.view.stop()
                        except Exception as e:
                            logger.debug("Failed to stop menu view after selection: %s", e)
                    # Now create channel
                    # Determine category: prefer option-specific category if configured and valid
                    sel_category = None
                    try:
                        cat_id = selected.get("category_id") if isinstance(selected, dict) else None
                        if cat_id:
                            guild = self.outer_thread.bot.modmail_guild
                            if guild:
                                ch = guild.get_channel(cat_id)
                                if isinstance(ch, discord.CategoryChannel):
                                    sel_category = ch
                    except Exception:
                        sel_category = None
                    # Fallback to provided category (from outer scope) or main category
                    fallback_category = category or self.outer_thread.bot.main_category
                    use_category = sel_category or fallback_category
                    # If confirmation is enabled, prompt now (after option selection)
                    try:
                        if self.outer_thread.bot.config.get("confirm_thread_creation"):
                            dest = message.channel if manual_trigger else recipient
                            view = ConfirmThreadCreationView()
                            view.add_item(
                                AcceptButton(
                                    "accept-thread-creation",
                                    self.outer_thread.bot.config["confirm_thread_creation_accept"],
                                )
                            )
                            view.add_item(
                                DenyButton(
                                    "deny-thread-creation",
                                    self.outer_thread.bot.config["confirm_thread_creation_deny"],
                                )
                            )
                            confirm = await dest.send(
                                embed=discord.Embed(
                                    title=self.outer_thread.bot.config["confirm_thread_creation_title"],
                                    description=self.outer_thread.bot.config["confirm_thread_response"],
                                    color=self.outer_thread.bot.main_color,
                                ),
                                view=view,
                            )
                            await view.wait()
                            if view.value is None:
                                # Timed out
                                self.outer_thread.cancelled = True
                                try:
                                    await dest.send(
                                        embed=discord.Embed(
                                            title=self.outer_thread.bot.config["thread_cancelled"],
                                            description="Timed out",
                                            color=self.outer_thread.bot.error_color,
                                        )
                                    )
                                    await confirm.edit(view=None)
                                except Exception:
                                    logger.warning(
                                        "Failed notifying user of thread creation timeout.",
                                        exc_info=True,
                                    )
                            elif view.value is False:
                                self.outer_thread.cancelled = True
                                try:
                                    await dest.send(
                                        embed=discord.Embed(
                                            title=self.outer_thread.bot.config["thread_cancelled"],
                                            color=self.outer_thread.bot.error_color,
                                        )
                                    )
                                except Exception:
                                    logger.warning(
                                        "Failed notifying user of thread creation denial.",
                                        exc_info=True,
                                    )
                            if self.outer_thread.cancelled:
                                # Clear pending/menu state and cache
                                try:
                                    setattr(self.outer_thread, "_pending_menu", False)
                                    self.outer_thread.manager.cache.pop(self.outer_thread.id, None)
                                except Exception:
                                    logger.debug(
                                        "Failed clearing pending menu/cache after cancellation.",
                                        exc_info=True,
                                    )
                                return
                    except Exception:
                        # If confirm step fails, proceed to create thread to avoid dead-ends
                        logger.warning("Confirm step failed after menu selection; continuing.")

                    self.outer_thread.bot.loop.create_task(
                        self.outer_thread.setup(
                            creator=creator,
                            category=use_category,
                            initial_message=message,
                        )
                    )
                    # Wait until channel is ready, then forward the original message like usual
                    try:
                        await self.outer_thread.wait_until_ready()
                        # Edge-case: unsnoozed restore might have re-created the channel but genesis send failed; ensure ready channel exists
                        if not self.outer_thread.channel:
                            logger.warning("Thread has no channel after unsnooze+selection; abort relay.")
                            setattr(self.outer_thread, "_pending_menu", False)
                            return
                        # Forward the user's initial DM to the thread channel
                        try:
                            await self.outer_thread.send(message)
                        except Exception:
                            logger.error(
                                "Failed to relay initial message after menu selection",
                                exc_info=True,
                            )
                        else:
                            # React to the user's DM with the 'sent' emoji
                            try:
                                (
                                    sent_emoji,
                                    _,
                                ) = await self.outer_thread.bot.retrieve_emoji()
                                await self.outer_thread.bot.add_reaction(message, sent_emoji)
                            except Exception as e:
                                logger.debug(
                                    "Failed to add sent reaction to user's DM: %s",
                                    e,
                                )
                            # Dispatch thread_reply event for parity
                            self.outer_thread.bot.dispatch(
                                "thread_reply",
                                self.outer_thread,
                                False,
                                message,
                                False,
                                False,
                            )
                        # Clear pending flag
                        setattr(self.outer_thread, "_pending_menu", False)
                    except Exception:
                        logger.warning(
                            "Unhandled failure after menu selection while waiting for channel readiness.",
                            exc_info=True,
                        )
                    # Invoke command callback AFTER channel ready if type == command
                    if selected and selected.get("type") == "command":
                        alias = selected.get("callback")
                        if alias:
                            from discord.ext.commands.view import StringView
                            from core.utils import normalize_alias

                            ctxs = []
                            for al in normalize_alias(alias):
                                view_ = StringView(self.outer_thread.bot.prefix + al)
                                # Create a synthetic message object that makes the bot appear
                                # as the author for menu-invoked command replies so the user
                                # selecting the option is not shown as a "mod" sender.
                                synthetic = DummyMessage(copy.copy(message))
                                try:
                                    synthetic.author = (
                                        self.outer_thread.bot.modmail_guild.me or self.outer_thread.bot.user
                                    )
                                except Exception:
                                    synthetic.author = self.outer_thread.bot.user
                                # Mark this message as menu-invoked for downstream formatting
                                setattr(synthetic, "_menu_invoked", True)
                                ctx_ = commands.Context(
                                    prefix=self.outer_thread.bot.prefix,
                                    view=view_,
                                    bot=self.outer_thread.bot,
                                    message=synthetic,
                                )
                                ctx_.thread = self.outer_thread
                                discord.utils.find(
                                    view_.skip_string,
                                    await self.outer_thread.bot.get_prefix(),
                                )
                                ctx_.invoked_with = view_.get_word().lower()
                                ctx_.command = self.outer_thread.bot.all_commands.get(ctx_.invoked_with)
                                # Mark context so downstream send/reply logic can treat as system/bot
                                setattr(ctx_, "_menu_invoked", True)
                                ctxs.append(ctx_)
                            for ctx_ in ctxs:
                                if ctx_.command:
                                    old_checks = copy.copy(ctx_.command.checks)
                                    ctx_.command.checks = [checks.has_permissions(PermissionLevel.INVALID)]
                                    try:
                                        await self.outer_thread.bot.invoke(ctx_)
                                    finally:
                                        ctx_.command.checks = old_checks

            class _ThreadCreationMenuView(discord.ui.View):
                def __init__(self, outer_thread: Thread):
                    super().__init__(timeout=timeout)
                    self.outer_thread = outer_thread
                    self.add_item(_ThreadCreationMenuSelect(outer_thread))

                async def on_timeout(self):
                    # Timeout -> abort thread creation
                    if self.outer_thread.bot.config.get("thread_creation_menu_close_on_timeout"):
                        try:
                            # Replace the entire embed with a minimal one containing only the timeout text
                            try:
                                color = (menu_msg.embeds[0].color if menu_msg.embeds else None) or getattr(
                                    self.outer_thread.bot, "mod_color", None
                                )
                            except Exception:
                                color = getattr(self.outer_thread.bot, "mod_color", None)
                            timeout_embed = (
                                discord.Embed(
                                    description="Menu timed out. Please send a new message to start again.",
                                    color=color,
                                )
                                if color
                                else discord.Embed(
                                    description="Menu timed out. Please send a new message to start again."
                                )
                            )
                            await menu_msg.edit(content=None, embed=timeout_embed, view=None)
                        except Exception:
                            logger.info(
                                "Failed editing menu message on timeout (close_on_timeout enabled).",
                                exc_info=True,
                            )
                        # remove thread from cache
                        try:
                            self.outer_thread.manager.cache.pop(self.outer_thread.id, None)
                        except Exception:
                            logger.debug(
                                "Failed popping thread from cache on timeout (close_on_timeout).",
                                exc_info=True,
                            )
                        # Clear pending menu flag so a new message can recreate a fresh thread
                        setattr(self.outer_thread, "_pending_menu", False)
                        self.outer_thread.cancelled = True
                    else:
                        try:
                            # Replace the entire embed with a minimal one containing only the timeout text
                            try:
                                color = (menu_msg.embeds[0].color if menu_msg.embeds else None) or getattr(
                                    self.outer_thread.bot, "mod_color", None
                                )
                            except Exception:
                                color = getattr(self.outer_thread.bot, "mod_color", None)
                            timeout_embed = (
                                discord.Embed(
                                    description="Menu timed out. Please send a new message to start again.",
                                    color=color,
                                )
                                if color
                                else discord.Embed(
                                    description="Menu timed out. Please send a new message to start again."
                                )
                            )
                            await menu_msg.edit(content=None, embed=timeout_embed, view=None)
                        except Exception:
                            logger.info(
                                "Failed editing menu message on timeout (keep alive mode).",
                                exc_info=True,
                            )
                        # Allow subsequent messages to trigger a new menu/thread by clearing state
                        setattr(self.outer_thread, "_pending_menu", False)
                        try:
                            self.outer_thread.manager.cache.pop(self.outer_thread.id, None)
                        except Exception:
                            logger.debug(
                                "Failed popping thread from cache on timeout (keep alive mode).",
                                exc_info=True,
                            )
                        self.outer_thread.cancelled = True
                    # Ensure view is stopped to release any internal tasks
                    try:
                        self.stop()
                    except Exception:
                        logger.debug(
                            "Failed stopping ThreadCreationMenuView on timeout.",
                            exc_info=True,
                        )

            # Send DM prompt
            try:
                # Build embed with new customizable settings
                try:
                    embed_title = self.bot.config.get("thread_creation_menu_embed_title")
                    embed_footer = self.bot.config.get("thread_creation_menu_embed_footer")
                    embed_thumb = self.bot.config.get("thread_creation_menu_embed_thumbnail_url")
                    embed_image = self.bot.config.get("thread_creation_menu_embed_image_url")
                    embed_footer_icon = self.bot.config.get("thread_creation_menu_embed_footer_icon_url")
                    embed_color_raw = self.bot.config.get("thread_creation_menu_embed_color")
                except Exception:
                    embed_title = None
                    embed_footer = None
                    embed_thumb = None
                    embed_image = None
                    embed_footer_icon = None
                    embed_color_raw = None
                embed_color = embed_color_raw or self.bot.mod_color
                embed = discord.Embed(title=embed_title, description=embed_text, color=embed_color)
                if embed_footer:
                    try:
                        if embed_footer_icon:
                            embed.set_footer(text=embed_footer, icon_url=embed_footer_icon)
                        else:
                            embed.set_footer(text=embed_footer)
                    except Exception as e:
                        logger.debug("Footer build failed (ignored): %s", e)
                # Option A: prefer dedicated large image when provided
                if embed_image:
                    try:
                        embed.set_image(url=embed_image)
                    except Exception as e:
                        logger.debug("Image set failed (ignored): %s", e)
                elif embed_thumb:
                    try:
                        embed.set_thumbnail(url=embed_thumb)
                    except Exception as e:
                        logger.debug("Thumbnail set failed (ignored): %s", e)
                menu_view = _ThreadCreationMenuView(thread)
                menu_msg = await recipient.send(embed=embed, view=menu_view)
                # mark thread as pending menu selection
                thread._pending_menu = True
                # Explicitly attach the message to the view for safety in callbacks
                try:
                    menu_view.message = menu_msg
                except Exception as e:
                    logger.info(
                        "Failed attaching menu message reference (initial menu send): %s",
                        e,
                    )
                # Store for later disabling on thread close
                try:
                    thread._dm_menu_msg_id = menu_msg.id
                    thread._dm_menu_channel_id = menu_msg.channel.id
                except Exception as e:
                    logger.info(
                        "Failed storing DM menu identifiers (initial menu send): %s",
                        e,
                    )
            except Exception:
                logger.warning(
                    "Failed to send thread-creation menu DM, falling back to immediate thread creation.",
                    exc_info=True,
                )
                self.bot.loop.create_task(
                    thread.setup(creator=creator, category=category, initial_message=message)
                )
            return thread

        # If menu is enabled but precreate is requested, send the menu DM but do NOT defer creation.
        # Selection becomes optional; thread channel will already be created below.
        if adv_enabled and user_initiated and precreate:
            try:
                embed_text = self.bot.config.get("thread_creation_menu_embed_text")
                placeholder = self.bot.config.get("thread_creation_menu_dropdown_placeholder")
                timeout = int(self.bot.config.get("thread_creation_menu_timeout") or 20)
            except Exception:
                embed_text = "Please select an option."
                placeholder = "Select an option to contact the staff team."
                timeout = 20

            options = self.bot.config.get("thread_creation_menu_options") or {}

            class _PrecreateMenuSelect(discord.ui.Select):
                def __init__(self, outer_thread: Thread):
                    self.outer_thread = outer_thread
                    opts = [
                        discord.SelectOption(
                            label=o["label"],
                            description=o["description"],
                            emoji=o["emoji"],
                        )
                        for o in options.values()
                    ]
                    super().__init__(
                        placeholder=placeholder,
                        min_values=1,
                        max_values=1,
                        options=opts,
                    )

                async def callback(self, interaction: discord.Interaction):
                    await interaction.response.defer(ephemeral=False)
                    # If thread somehow got snoozed before selection in precreate flow (rare), restore first.
                    try:
                        if self.outer_thread.snoozed:
                            await self.outer_thread.restore_from_snooze()
                    except Exception:
                        logger.warning(
                            "Failed unsnoozing thread prior to precreate menu selection; continuing.",
                            exc_info=True,
                        )
                    chosen_label = self.values[0]
                    key = chosen_label.lower().replace(" ", "_")
                    selected = options.get(key)
                    self.outer_thread._selected_thread_creation_menu_option = selected
                    # Remove the view
                    try:
                        msg = getattr(interaction, "message", None)
                        if msg is None and self.view and hasattr(self.view, "message"):
                            msg = self.view.message
                        if msg is not None:
                            # Replace entire embed so only the selection line remains
                            try:
                                base_color = (msg.embeds[0].color if msg.embeds else None) or getattr(
                                    self.outer_thread.bot, "mod_color", None
                                )
                            except Exception:
                                base_color = getattr(self.outer_thread.bot, "mod_color", None)
                            selection_embed = (
                                discord.Embed(
                                    description=f"You selected: {chosen_label}",
                                    color=base_color,
                                )
                                if base_color is not None
                                else discord.Embed(description=f"You selected: {chosen_label}")
                            )
                            await msg.edit(content=None, embed=selection_embed, view=None)
                        else:
                            try:
                                await interaction.edit_original_response(
                                    content=f"You selected: {chosen_label}", view=None
                                )
                            except Exception:
                                await interaction.edit_original_response(view=None)
                    except Exception:
                        try:
                            await interaction.edit_original_response(view=None)
                        except Exception:
                            logger.debug(
                                "Failed secondary edit_original_response path removing view.",
                                exc_info=True,
                            )
                    if self.view:
                        try:
                            self.view.stop()
                        except Exception:
                            logger.debug(
                                "Failed removing view after selection (stop).",
                                exc_info=True,
                            )
                    # Log selection to thread channel if configured
                    try:
                        await self.outer_thread.wait_until_ready()
                        if self.outer_thread.bot.config.get("thread_creation_menu_selection_log"):
                            opt = selected or {}
                            log_txt = f"Selected menu option: {opt.get('label')} ({opt.get('type')})"
                            if opt.get("type") == "command":
                                log_txt += f" -> {opt.get('callback')}"
                            await self.outer_thread.channel.send(
                                embed=discord.Embed(
                                    description=log_txt,
                                    color=self.outer_thread.bot.mod_color,
                                )
                            )
                        # If a category_id is set on the option, move the channel accordingly
                        try:
                            cat_id = selected.get("category_id") if isinstance(selected, dict) else None
                            if cat_id:
                                guild = self.outer_thread.bot.modmail_guild
                                target = guild and guild.get_channel(int(cat_id))
                                if isinstance(target, discord.CategoryChannel):
                                    await self.outer_thread.channel.edit(
                                        category=target,
                                        reason="Menu selection: move to category",
                                    )
                        except Exception:
                            logger.debug(
                                "Failed moving thread channel based on selected category_id.",
                                exc_info=True,
                            )
                    except Exception:
                        logger.debug(
                            "Failed logging menu selection or moving category in precreate flow.",
                            exc_info=True,
                        )
                    # If the option type is command, invoke it now within the created thread
                    if selected and selected.get("type") == "command":
                        alias = selected.get("callback")
                        if alias:
                            from discord.ext.commands.view import StringView
                            from core.utils import normalize_alias

                            ctxs = []
                            for al in normalize_alias(alias):
                                view_ = StringView(self.outer_thread.bot.prefix + al)
                                synthetic = DummyMessage(copy.copy(message))
                                try:
                                    synthetic.author = (
                                        self.outer_thread.bot.modmail_guild.me or self.outer_thread.bot.user
                                    )
                                except Exception:
                                    synthetic.author = self.outer_thread.bot.user
                                setattr(synthetic, "_menu_invoked", True)
                                ctx_ = commands.Context(
                                    prefix=self.outer_thread.bot.prefix,
                                    view=view_,
                                    bot=self.outer_thread.bot,
                                    message=synthetic,
                                )
                                ctx_.thread = self.outer_thread
                                discord.utils.find(
                                    view_.skip_string,
                                    await self.outer_thread.bot.get_prefix(),
                                )
                                ctx_.invoked_with = view_.get_word().lower()
                                ctx_.command = self.outer_thread.bot.all_commands.get(ctx_.invoked_with)
                                setattr(ctx_, "_menu_invoked", True)
                                ctxs.append(ctx_)
                            for ctx_ in ctxs:
                                if ctx_.command:
                                    old_checks = copy.copy(ctx_.command.checks)
                                    ctx_.command.checks = [checks.has_permissions(PermissionLevel.INVALID)]
                                    try:
                                        await self.outer_thread.bot.invoke(ctx_)
                                    finally:
                                        ctx_.command.checks = old_checks

            class _PrecreateMenuView(discord.ui.View):
                def __init__(self, outer_thread: Thread):
                    super().__init__(timeout=timeout)
                    self.add_item(_PrecreateMenuSelect(outer_thread))

                async def on_timeout(self):
                    try:
                        # Replace the entire embed with a minimal one containing only the timeout text
                        try:
                            color = menu_msg.embeds[0].color if menu_msg.embeds else None
                        except Exception:
                            color = None
                        timeout_embed = (
                            discord.Embed(
                                description="Menu timed out. Please send a new message to start again.",
                                color=color,
                            )
                            if color
                            else discord.Embed(
                                description="Menu timed out. Please send a new message to start again."
                            )
                        )
                        await menu_msg.edit(content=None, embed=timeout_embed, view=None)
                    except Exception:
                        logger.info(
                            "Failed editing precreate menu message on timeout.",
                            exc_info=True,
                        )
                    try:
                        self.stop()
                    except Exception:
                        logger.debug(
                            "Failed stopping PrecreateMenuView on timeout.",
                            exc_info=True,
                        )

            try:
                # Build embed with new customizable settings (precreate flow)
                try:
                    embed_title = self.bot.config.get("thread_creation_menu_embed_title")
                    embed_footer = self.bot.config.get("thread_creation_menu_embed_footer")
                    embed_thumb = self.bot.config.get("thread_creation_menu_embed_thumbnail_url")
                    embed_image = self.bot.config.get("thread_creation_menu_embed_image_url")
                    embed_large = bool(self.bot.config.get("thread_creation_menu_embed_large_image"))
                    embed_footer_icon = self.bot.config.get("thread_creation_menu_embed_footer_icon_url")
                    embed_color_raw = self.bot.config.get("thread_creation_menu_embed_color")
                except Exception:
                    embed_title = None
                    embed_footer = None
                    embed_thumb = None
                    embed_image = None
                    embed_large = False
                    embed_footer_icon = None
                    embed_color_raw = None
                embed_color = embed_color_raw or self.bot.mod_color
                embed = discord.Embed(title=embed_title, description=embed_text, color=embed_color)
                if embed_footer:
                    try:
                        if embed_footer_icon:
                            embed.set_footer(text=embed_footer, icon_url=embed_footer_icon)
                        else:
                            embed.set_footer(text=embed_footer)
                    except Exception as e:
                        logger.debug("Footer build failed (ignored precreate): %s", e)
                if embed_image:
                    try:
                        embed.set_image(url=embed_image)
                    except Exception as e:
                        logger.debug("Image set failed (ignored precreate): %s", e)
                elif embed_thumb:
                    try:
                        if embed_large:
                            embed.set_image(url=embed_thumb)
                        else:
                            embed.set_thumbnail(url=embed_thumb)
                    except Exception as e:
                        logger.debug("Thumbnail/image set failed (ignored precreate): %s", e)
                menu_view = _PrecreateMenuView(thread)
                # Send menu DM AFTER channel creation initiation (channel will be created below)
                menu_msg = await recipient.send(embed=embed, view=menu_view)
                try:
                    menu_view.message = menu_msg
                except Exception:
                    logger.debug(
                        "Failed attaching menu message reference (precreate menu).",
                        exc_info=True,
                    )
                # Store for later disabling on thread close
                try:
                    thread._dm_menu_msg_id = menu_msg.id
                    thread._dm_menu_channel_id = menu_msg.channel.id
                except Exception:
                    logger.debug(
                        "Failed storing DM menu identifiers (precreate menu).",
                        exc_info=True,
                    )
            except Exception:
                logger.debug("Failed to send precreate menu DM; proceeding without menu.")

        # Regular immediate creation (force main_category for user-initiated menu flows)
        forced_category = None
        if adv_enabled and user_initiated and precreate:
            # In precreate mode we still create immediately (main category override optional)
            forced_category = self.bot.main_category
        chosen_category = forced_category or category
        self.bot.loop.create_task(
            thread.setup(creator=creator, category=chosen_category, initial_message=message)
        )
        return thread

    async def find_or_create(self, recipient) -> Thread:
        return await self.find(recipient=recipient) or await self.create(recipient)
