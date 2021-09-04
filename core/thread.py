import asyncio
import copy
import io
import re
import time
import typing
from datetime import datetime, timedelta
from types import SimpleNamespace

import isodate

import discord
from discord.ext.commands import MissingRequiredArgument, CommandError

from core.models import DMDisabled, DummyMessage, getLogger
from core.time import human_timedelta
from core.utils import (
    is_image_url,
    days,
    match_title,
    match_user_id,
    match_other_recipients,
    truncate,
    get_top_hoisted_role,
    create_thread_channel,
    get_joint_id,
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
        self.genesis_message = None
        self._ready_event = asyncio.Event()
        self.wait_tasks = []
        self.close_task = None
        self.auto_close_task = None
        self._cancelled = False

    def __repr__(self):
        return f'Thread(recipient="{self.recipient or self.id}", channel={self.channel.id}, other_recipients={len(self._other_recipients)})'

    def __eq__(self, other):
        if isinstance(other, Thread):
            return self.id == other.id
        return super().__eq__(other)

    async def wait_until_ready(self) -> None:
        """Blocks execution until the thread is fully set up."""
        # timeout after 30 seconds
        task = asyncio.create_task(asyncio.wait_for(self._ready_event.wait(), timeout=25))
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

    @classmethod
    async def from_channel(cls, manager: "ThreadManager", channel: discord.TextChannel) -> "Thread":
        recipient_id = match_user_id(
            channel.topic
        )  # there is a chance it grabs from another recipient's main thread

        if recipient_id in manager.cache:
            thread = manager.cache[recipient_id]
        else:
            recipient = manager.bot.get_user(recipient_id) or await manager.bot.fetch_user(recipient_id)

            other_recipients = []
            for uid in match_other_recipients(channel.topic):
                try:
                    other_recipient = manager.bot.get_user(uid) or await manager.bot.fetch_user(uid)
                except discord.NotFound:
                    continue
                other_recipients.append(other_recipient)

            thread = cls(manager, recipient or recipient_id, channel, other_recipients)

        return thread

    async def setup(self, *, creator=None, category=None, initial_message=None):
        """Create the thread channel and other io related initialisation tasks"""
        self.bot.dispatch("thread_initiate", self, creator, category, initial_message)
        recipient = self.recipient

        # in case it creates a channel outside of category
        overwrites = {self.bot.modmail_guild.default_role: discord.PermissionOverwrite(read_messages=False)}

        category = category or self.bot.main_category

        if category is not None:
            overwrites = None

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

        await channel.edit(topic=f"User ID: {recipient.id}")
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
                self.genesis_message = msg
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

            embed.set_footer(text=footer, icon_url=self.bot.guild.icon_url)
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
                def store_user(self, user):
                    return user

            for note in notes:
                author = note["author"]

                class Author:
                    name = author["name"]
                    id = author["id"]
                    discriminator = author["discriminator"]
                    avatar_url = author["avatar_url"]

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
                message = discord.Message(state=State(), channel=None, data=data)
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
        time = datetime.utcnow()

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

        created = str((time - user.created_at).days)
        user_info = []
        if self.bot.config["thread_show_account_age"]:
            user_info.append(f"was created {days(created)}")

        embed = discord.Embed(color=color, description=user.mention, timestamp=time)

        if user.dm_channel:
            footer = f"User ID: {user.id} • DM ID: {user.dm_channel.id}"
        else:
            footer = f"User ID: {user.id}"

        embed.set_author(name=str(user), icon_url=user.avatar_url, url=log_url)
        # embed.set_thumbnail(url=avi)

        if member is not None:
            joined = str((time - member.joined_at).days)
            # embed.add_field(name='Joined', value=joined + days(joined))
            if self.bot.config["thread_show_join_age"]:
                user_info.append(f"joined {days(joined)}")

            if member.nick:
                embed.add_field(name="Nickname", value=member.nick, inline=True)
            if role_names:
                embed.add_field(name="Roles", value=role_names, inline=True)
            embed.set_footer(text=footer)
        else:
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

    def _close_after(self, closer, silent, delete_channel, message):
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
            now = datetime.utcnow()
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

            task = self.bot.loop.call_later(after, self._close_after, closer, silent, delete_channel, message)

            if auto_close:
                self.auto_close_task = task
            else:
                self.close_task = task
        else:
            await self._close(closer, silent, delete_channel, message)

    async def _close(self, closer, silent=False, delete_channel=True, message=None, scheduled=False):
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
                    "closed_at": str(datetime.utcnow()),
                    "nsfw": self.channel.nsfw,
                    "close_message": message,
                    "closer": {
                        "id": str(closer.id),
                        "name": closer.name,
                        "discriminator": closer.discriminator,
                        "avatar_url": str(closer.avatar_url),
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
        embed.set_footer(text=f"{event} by {_closer}", icon_url=closer.avatar_url)
        embed.timestamp = datetime.utcnow()

        tasks = [self.bot.config.update()]

        if self.bot.log_channel is not None and self.channel is not None:
            tasks.append(self.bot.log_channel.send(embed=embed))

        # Thread closed message

        embed = discord.Embed(
            title=self.bot.config["thread_close_title"],
            color=self.bot.error_color,
        )
        if self.bot.config["show_timestamp"]:
            embed.timestamp = datetime.utcnow()

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
        embed.set_footer(text=footer, icon_url=self.bot.guild.icon_url)

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

        if delete_channel:
            tasks.append(self.channel.delete())

        await asyncio.gather(*tasks)
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
        reset_time = datetime.utcnow() + timedelta(seconds=seconds)
        human_time = human_timedelta(dt=reset_time)

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

            if message1.embeds[0].color.value == self.bot.main_color and (
                message1.embeds[0].author.name.startswith("Note")
                or message1.embeds[0].author.name.startswith("Persistent Note")
            ):
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
        if message2 is not [None]:
            for m2 in message2:
                embed2 = m2.embeds[0]
                embed2.description = message
                tasks += [m2.edit(embed=embed2)]
        elif message1.embeds[0].author.name.startswith("Persistent Note"):
            tasks += [self.bot.api.edit_note(message1.id, message)]

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

        if message1.embeds[0].author.name.startswith("Persistent Note"):
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
        if not message.content and not message.attachments:
            raise MissingRequiredArgument(SimpleNamespace(name="msg"))

        msg = await self.send(
            message,
            self.channel,
            note=True,
            persistent_note=persistent,
            thread_creation=thread_creation,
        )

        self.bot.loop.create_task(
            self.bot.api.append_log(message, message_id=msg.id, channel_id=self.channel.id, type_="system")
        )

        return msg

    async def reply(
        self, message: discord.Message, anonymous: bool = False, plain: bool = False
    ) -> typing.Tuple[discord.Message, discord.Message]:
        if not message.content and not message.attachments:
            raise MissingRequiredArgument(SimpleNamespace(name="msg"))
        if not any(g.get_member(self.id) for g in self.bot.guilds):
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
            tasks.append(
                message.channel.send(
                    embed=discord.Embed(
                        color=self.bot.error_color,
                        description=description,
                    )
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

        author = message.author

        embed = discord.Embed(description=message.content)
        if self.bot.config["show_timestamp"]:
            embed.timestamp = message.created_at

        system_avatar_url = "https://discordapp.com/assets/f78426a064bc9dd24847519259bc42af.png"

        if not note:
            if anonymous and from_mod and not isinstance(destination, discord.TextChannel):
                # Anonymously sending to the user.
                tag = self.bot.config["mod_tag"]
                if tag is None:
                    tag = str(get_top_hoisted_role(author))
                name = self.bot.config["anon_username"]
                if name is None:
                    name = tag
                avatar_url = self.bot.config["anon_avatar_url"]
                if avatar_url is None:
                    avatar_url = self.bot.guild.icon_url
                embed.set_author(
                    name=name,
                    icon_url=avatar_url,
                    url=f"https://discordapp.com/channels/{self.bot.guild.id}#{message.id}",
                )
            else:
                # Normal message
                name = str(author)
                avatar_url = author.avatar_url
                embed.set_author(
                    name=name,
                    icon_url=avatar_url,
                    url=f"https://discordapp.com/users/{author.id}#{message.id}",
                )
        else:
            # Special note messages
            embed.set_author(
                name=f"{'Persistent' if persistent_note else ''} Note ({author.name})",
                icon_url=system_avatar_url,
                url=f"https://discordapp.com/users/{author.id}#{message.id}",
            )

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
        images.extend(
            (
                str(i.image_url) if isinstance(i.image_url, discord.Asset) else i.image_url,
                f"{i.name} Sticker",
                True,
            )
            for i in message.stickers
        )

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
                            description = "Unable to retrieve sticker image"
                        else:
                            description = "\u200b"
                        embed.add_field(name=filename, value=description)
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
            embed.colour = self.bot.mod_color
            # Anonymous reply sent in thread channel
            if anonymous and isinstance(destination, discord.TextChannel):
                embed.set_footer(text="Anonymous Reply")
            # Normal messages
            elif not anonymous:
                mod_tag = self.bot.config["mod_tag"]
                if mod_tag is None:
                    mod_tag = str(get_top_hoisted_role(message.author))
                embed.set_footer(text=mod_tag)  # Normal messages
            else:
                embed.set_footer(text=self.bot.config["anon_tag"])
        elif note:
            embed.colour = self.bot.main_color
        else:
            embed.set_footer(text=f"Message ID: {message.id}")
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

        try:
            await destination.trigger_typing()
        except discord.NotFound:
            logger.warning("Channel not found.")
            raise

        if not from_mod and not note:
            mentions = self.get_notifications()
        else:
            mentions = None

        if plain:
            if from_mod and not isinstance(destination, discord.TextChannel):
                # Plain to user
                if embed.footer.text:
                    plain_message = f"**({embed.footer.text}) "
                else:
                    plain_message = "**"
                plain_message += f"{embed.author.name}:** {embed.description}"
                files = []
                for i in embed.fields:
                    if "Image" in i.name:
                        async with self.bot.session.get(i.field[i.field.find("http") : -1]) as resp:
                            stream = io.BytesIO(await resp.read())
                            files.append(discord.File(stream))

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

    def get_notifications(self) -> str:
        key = str(self.id)

        mentions = []
        mentions.extend(self.bot.config["subscriptions"].get(key, []))

        if key in self.bot.config["notification_squad"]:
            mentions.extend(self.bot.config["notification_squad"][key])
            self.bot.config["notification_squad"].pop(key)
            self.bot.loop.create_task(self.bot.config.update())

        return " ".join(set(mentions))

    async def set_title(self, title: str) -> None:
        user_id = match_user_id(self.channel.topic)
        ids = ",".join(i.id for i in self._other_recipients)

        await self.channel.edit(topic=f"Title: {title}\nUser ID: {user_id}\nOther Recipients: {ids}")

    async def add_users(self, users: typing.List[typing.Union[discord.Member, discord.User]]) -> None:
        title = match_title(self.channel.topic)
        user_id = match_user_id(self.channel.topic)
        self._other_recipients += users

        ids = ",".join(str(i.id) for i in self._other_recipients)
        await self.channel.edit(topic=f"Title: {title}\nUser ID: {user_id}\nOther Recipients: {ids}")

    async def remove_users(self, users: typing.List[typing.Union[discord.Member, discord.User]]) -> None:
        title = match_title(self.channel.topic)
        user_id = match_user_id(self.channel.topic)
        for u in users:
            self._other_recipients.remove(u)

        ids = ",".join(str(i.id) for i in self._other_recipients)
        await self.channel.edit(topic=f"Title: {title}\nUser ID: {user_id}\nOther Recipients: {ids}")


class ThreadManager:
    """Class that handles storing, finding and creating Modmail threads."""

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}

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
        if recipient is None and channel is not None:
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
                if not thread.cancelled and (
                    not thread.channel or not self.bot.get_channel(thread.channel.id)
                ):
                    logger.warning("Found existing thread for %s but the channel is invalid.", recipient_id)
                    await thread.close(closer=self.bot.user, silent=True, delete_channel=False)
                    thread = None
        else:
            channel = discord.utils.find(
                lambda x: str(recipient_id) in x.topic if x.topic else False,
                self.bot.modmail_guild.text_channels,
            )

            if channel:
                thread = await Thread.from_channel(self, channel)
                if thread.recipient:
                    # only save if data is valid
                    self.cache[recipient_id] = thread
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
        user_id = -1

        if channel.topic:
            user_id = match_user_id(channel.topic)

        if user_id == -1:
            return None

        if user_id in self.cache:
            return self.cache[user_id]

        try:
            recipient = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        except discord.NotFound:
            recipient = None

        other_recipients = []
        for uid in match_other_recipients(channel.topic):
            try:
                other_recipient = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
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
            confirm = await destination.send(
                embed=discord.Embed(
                    title=self.bot.config["confirm_thread_creation_title"],
                    description=self.bot.config["confirm_thread_response"],
                    color=self.bot.main_color,
                )
            )
            accept_emoji = self.bot.config["confirm_thread_creation_accept"]
            deny_emoji = self.bot.config["confirm_thread_creation_deny"]
            emojis = [accept_emoji, deny_emoji]
            for emoji in emojis:
                await confirm.add_reaction(emoji)
                await asyncio.sleep(0.2)

            try:
                r, _ = await self.bot.wait_for(
                    "reaction_add",
                    check=lambda r, u: u.id == recipient.id
                    and r.message.id == confirm.id
                    and r.message.channel.id == confirm.channel.id
                    and str(r.emoji) in (accept_emoji, deny_emoji),
                    timeout=20,
                )
            except asyncio.TimeoutError:
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
            else:
                if str(r.emoji) == deny_emoji:
                    thread.cancelled = True
                    self.bot.loop.create_task(
                        destination.send(
                            embed=discord.Embed(
                                title=self.bot.config["thread_cancelled"], color=self.bot.error_color
                            )
                        )
                    )

            async def remove_reactions():
                for emoji in emojis:
                    await confirm.remove_reaction(emoji, self.bot.user)
                    await asyncio.sleep(0.2)

            self.bot.loop.create_task(remove_reactions())
            if thread.cancelled:
                del self.cache[recipient.id]
                return thread

        self.bot.loop.create_task(thread.setup(creator=creator, category=category, initial_message=message))
        return thread

    async def find_or_create(self, recipient) -> Thread:
        return await self.find(recipient=recipient) or await self.create(recipient)
