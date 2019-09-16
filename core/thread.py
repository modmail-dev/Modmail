import asyncio
import logging
import re
import string
import typing
from datetime import datetime, timedelta
from types import SimpleNamespace

import isodate

import discord
from discord.ext.commands import MissingRequiredArgument, CommandError

from core.time import human_timedelta
from core.utils import is_image_url, days, match_user_id, truncate, ignore, strtobool

logger = logging.getLogger("Modmail")


class Thread:
    """Represents a discord Modmail thread"""

    def __init__(
        self,
        manager: "ThreadManager",
        recipient: typing.Union[discord.Member, discord.User, int],
        channel: typing.Union[discord.DMChannel, discord.TextChannel] = None,
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
        self._channel = channel
        self.genesis_message = None
        self._ready_event = asyncio.Event()
        self.close_task = None
        self.auto_close_task = None

    def __repr__(self):
        return (
            f'Thread(recipient="{self.recipient or self.id}", '
            f"channel={self.channel.id})"
        )

    async def wait_until_ready(self) -> None:
        """Blocks execution until the thread is fully set up."""
        await self._ready_event.wait()

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
    def ready(self) -> bool:
        return self._ready_event.is_set()

    @ready.setter
    def ready(self, flag: bool):
        if flag:
            self._ready_event.set()
            self.bot.dispatch("thread_ready", self)
        else:
            self._ready_event.clear()

    async def setup(self, *, creator=None, category=None):
        """Create the thread channel and other io related initialisation tasks"""

        self.bot.dispatch("thread_create", self)

        recipient = self.recipient

        # in case it creates a channel outside of category
        overwrites = {
            self.bot.modmail_guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            )
        }

        category = category or self.bot.main_category

        if category is not None:
            overwrites = None

        try:
            channel = await self.bot.modmail_guild.create_text_channel(
                name=self.manager.format_channel_name(recipient),
                category=category,
                overwrites=overwrites,
                reason="Creating a thread channel.",
            )
        except discord.HTTPException as e:  # Failed to create due to 50 channel limit.
            logger.critical("An error occurred while creating a thread.", exc_info=True)
            self.manager.cache.pop(self.id)

            embed = discord.Embed(color=discord.Color.red())
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
            logger.error(
                "An error occurred while posting logs to the database.", exc_info=True
            )
            log_url = log_count = None
            # ensure core functionality still works

        if creator:
            mention = None
        else:
            mention = self.bot.config["mention"]

        async def send_genesis_message():
            info_embed = self._format_info_embed(
                recipient, log_url, log_count, discord.Color.green()
            )
            try:
                msg = await channel.send(mention, embed=info_embed)
                self.bot.loop.create_task(msg.pin())
                self.genesis_message = msg
            except Exception:
                logger.error("Failed unexpectedly:", exc_info=True)
            finally:
                self.ready = True

        await channel.edit(topic=f"User ID: {recipient.id}")
        self.bot.loop.create_task(send_genesis_message())

        # Once thread is ready, tell the recipient.
        thread_creation_response = self.bot.config["thread_creation_response"]

        embed = discord.Embed(
            color=self.bot.mod_color,
            description=thread_creation_response,
            timestamp=channel.created_at,
        )

        try:
            recipient_thread_close = strtobool(
                self.bot.config["recipient_thread_close"]
            )
        except ValueError:
            recipient_thread_close = self.bot.config.remove("recipient_thread_close")

        if recipient_thread_close:
            footer = self.bot.config["thread_self_closable_creation_footer"]
        else:
            footer = self.bot.config["thread_creation_footer"]

        embed.set_footer(text=footer, icon_url=self.bot.guild.icon_url)
        embed.title = self.bot.config["thread_creation_title"]

        if creator is None:
            msg = await recipient.send(embed=embed)

            if recipient_thread_close:
                close_emoji = self.bot.config["close_emoji"]
                close_emoji = await self.bot.convert_emoji(close_emoji)
                await msg.add_reaction(close_emoji)

    def _format_info_embed(self, user, log_url, log_count, color):
        """Get information about a member of a server
        supports users from the guild or not."""
        member = self.bot.guild.get_member(user.id)
        time = datetime.utcnow()

        # key = log_url.split('/')[-1]

        role_names = ""
        if member is not None:
            sep_server = self.bot.using_multiple_server_setup
            separator = ", " if sep_server else " "

            roles = []

            for role in sorted(member.roles, key=lambda r: r.position):
                if role.name == "@everyone":
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
        embed = discord.Embed(
            color=color,
            description=f"{user.mention} was created {days(created)}",
            timestamp=time,
        )

        # if not role_names:
        #     embed.add_field(name='Mention', value=user.mention)
        # embed.add_field(name='Registered', value=created + days(created))

        footer = "User ID: " + str(user.id)
        embed.set_author(name=str(user), icon_url=user.avatar_url, url=log_url)
        # embed.set_thumbnail(url=avi)

        if member is not None:
            joined = str((time - member.joined_at).days)
            # embed.add_field(name='Joined', value=joined + days(joined))
            embed.description += f", joined {days(joined)}"

            if member.nick:
                embed.add_field(name="Nickname", value=member.nick, inline=True)
            if role_names:
                embed.add_field(name="Roles", value=role_names, inline=True)
            embed.set_footer(text=footer)
        else:
            embed.set_footer(text=f"{footer} • (not in main server)")

        if log_count is not None:
            # embed.add_field(name='Past logs', value=f'{log_count}')
            thread = "thread" if log_count == 1 else "threads"
            embed.description += f" with **{log_count or 'no'}** past {thread}."
        else:
            embed.description += "."

        mutual_guilds = [g for g in self.bot.guilds if user in g.members]
        if member is None or len(mutual_guilds) > 1:
            embed.add_field(
                name="Mutual Server(s)", value=", ".join(g.name for g in mutual_guilds)
            )

        return embed

    def _close_after(self, closer, silent, delete_channel, message):
        return self.bot.loop.create_task(
            self._close(closer, silent, delete_channel, message, True)
        )

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

            task = self.bot.loop.call_later(
                after, self._close_after, closer, silent, delete_channel, message
            )

            if auto_close:
                self.auto_close_task = task
            else:
                self.close_task = task
        else:
            await self._close(closer, silent, delete_channel, message)

    async def _close(
        self, closer, silent=False, delete_channel=True, message=None, scheduled=False
    ):
        try:
            self.manager.cache.pop(self.id)
        except KeyError:
            logger.warning("Thread already closed.", exc_info=True)
            return

        await self.cancel_closure(all=True)

        # Cancel auto closing the thread if closed by any means.

        self.bot.config["subscriptions"].pop(str(self.id), None)
        self.bot.config["notification_squad"].pop(str(self.id), None)

        # Logging
        log_data = await self.bot.api.post_log(
            self.channel.id,
            {
                "open": False,
                "closed_at": str(datetime.utcnow()),
                "close_message": message if not silent else None,
                "closer": {
                    "id": str(closer.id),
                    "name": closer.name,
                    "discriminator": closer.discriminator,
                    "avatar_url": str(closer.avatar_url),
                    "mod": True,
                },
            },
        )

        if isinstance(log_data, dict):
            prefix = self.bot.config["log_url_prefix"].strip("/")
            if prefix == "NONE":
                prefix = ""
            log_url = f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{log_data['key']}"

            if log_data["messages"]:
                content = str(log_data["messages"][0]["content"])
                sneak_peak = content.replace("\n", "")
            else:
                sneak_peak = "No content"

            desc = f"[`{log_data['key']}`]({log_url}): "
            desc += truncate(sneak_peak, max=75 - 13)
        else:
            desc = "Could not resolve log url."
            log_url = None

        embed = discord.Embed(description=desc, color=discord.Color.red())

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
        # embed.set_author(name=f'Event: {event}', url=log_url)
        embed.set_footer(text=f"{event} by {_closer}")
        embed.timestamp = datetime.utcnow()

        tasks = [self.bot.config.update()]

        if self.bot.log_channel is not None:
            tasks.append(self.bot.log_channel.send(embed=embed))

        # Thread closed message

        embed = discord.Embed(
            title=self.bot.config["thread_close_title"],
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )

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

        if not silent and self.recipient is not None:
            tasks.append(self.recipient.send(embed=embed))

        if delete_channel:
            tasks.append(self.channel.delete())

        await asyncio.gather(*tasks)

    async def cancel_closure(
        self,
        auto_close: bool = False,
        all: bool = False,  # pylint: disable=redefined-builtin
    ) -> None:
        if self.close_task is not None and (not auto_close or all):
            self.close_task.cancel()
            self.close_task = None
        if self.auto_close_task is not None and (auto_close or all):
            self.auto_close_task.cancel()
            self.auto_close_task = None

        to_update = self.bot.config["closures"].pop(str(self.id), None)
        if to_update is not None:
            await self.bot.config.update()

    @staticmethod
    async def _find_thread_message(channel, message_id):
        async for msg in channel.history():
            if not msg.embeds:
                continue
            embed = msg.embeds[0]
            if embed and embed.author and embed.author.url:
                if str(message_id) == str(embed.author.url).split("/")[-1]:
                    return msg

    async def _fetch_timeout(
        self
    ) -> typing.Union[None, isodate.duration.Duration, timedelta]:
        """
        This grabs the timeout value for closing threads automatically
        from the ConfigManager and parses it for use internally.

        :returns: None if no timeout is set.
        """
        timeout = self.bot.config["thread_auto_close"]
        if timeout:
            try:
                timeout = isodate.parse_duration(timeout)
            except isodate.ISO8601Error:
                logger.warning(
                    "The auto_close_thread limit needs to be a "
                    "ISO-8601 duration formatted duration string "
                    'greater than 0 days, not "%s".',
                    str(timeout),
                )
                timeout = self.bot.config.remove("thread_auto_close")
                await self.bot.config.update()

        return timeout

    async def _restart_close_timer(self):
        """
        This will create or restart a timer to automatically close this
        thread.
        """
        timeout = await self._fetch_timeout()

        # Exit if timeout was not set
        if not timeout:
            return

        # Set timeout seconds
        seconds = timeout.total_seconds()
        # seconds = 20  # Uncomment to debug with just 20 seconds
        reset_time = datetime.utcnow() + timedelta(seconds=seconds)
        human_time = human_timedelta(dt=reset_time)

        try:
            thread_auto_close_silently = strtobool(
                self.bot.config["thread_auto_close_silently"]
            )
        except ValueError:
            thread_auto_close_silently = self.bot.config.remove(
                "thread_auto_close_silently"
            )

        if thread_auto_close_silently:
            return await self.close(
                closer=self.bot.user, silent=True, after=int(seconds), auto_close=True
            )

        # Grab message
        close_message = self.bot.formatter.format(
            self.bot.config["thread_auto_close_response"],
            timeout=human_time
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

    async def edit_message(self, message_id: int, message: str) -> None:
        recipient_msg, channel_msg = await asyncio.gather(
            self._find_thread_message(self.recipient, message_id),
            self._find_thread_message(self.channel, message_id),
        )

        channel_embed = channel_msg.embeds[0]
        channel_embed.description = message

        tasks = [channel_msg.edit(embed=channel_embed)]

        if recipient_msg:
            recipient_embed = recipient_msg.embeds[0]
            recipient_embed.description = message
            tasks.append(recipient_msg.edit(embed=recipient_embed))

        await asyncio.gather(*tasks)

    async def delete_message(self, message_id):
        msg_recipient, msg_channel = await asyncio.gather(
            self._find_thread_message(self.recipient, message_id),
            self._find_thread_message(self.channel, message_id),
        )
        await asyncio.gather(msg_recipient.delete(), msg_channel.delete())

    async def note(self, message: discord.Message) -> None:
        if not message.content and not message.attachments:
            raise MissingRequiredArgument(SimpleNamespace(name="msg"))

        _, msg = await asyncio.gather(
            self.bot.api.append_log(message, self.channel.id, type_="system"),
            self.send(message, self.channel, note=True),
        )

        return msg

    async def reply(self, message: discord.Message, anonymous: bool = False) -> None:
        if not message.content and not message.attachments:
            raise MissingRequiredArgument(SimpleNamespace(name="msg"))
        if not any(g.get_member(self.id) for g in self.bot.guilds):
            return await message.channel.send(
                embed=discord.Embed(
                    color=discord.Color.red(),
                    description="Your message could not be delivered since "
                    "the recipient shares no servers with the bot.",
                )
            )

        tasks = []

        try:
            await self.send(
                message, destination=self.recipient, from_mod=True, anonymous=anonymous
            )
        except Exception:
            logger.error("Message delivery failed:", exc_info=True)
            tasks.append(
                message.channel.send(
                    embed=discord.Embed(
                        color=discord.Color.red(),
                        description="Your message could not be delivered as "
                        "the recipient is only accepting direct "
                        "messages from friends, or the bot was "
                        "blocked by the recipient.",
                    )
                )
            )
        else:
            # Send the same thing in the thread channel.
            tasks.append(
                self.send(
                    message,
                    destination=self.channel,
                    from_mod=True,
                    anonymous=anonymous,
                )
            )

            tasks.append(
                self.bot.api.append_log(
                    message,
                    self.channel.id,
                    type_="anonymous" if anonymous else "thread_message",
                )
            )

            # Cancel closing if a thread message is sent.
            if self.close_task is not None:
                await self.cancel_closure()
                tasks.append(
                    self.channel.send(
                        embed=discord.Embed(
                            color=discord.Color.red(),
                            description="Scheduled close has been cancelled.",
                        )
                    )
                )

        await asyncio.gather(*tasks)

    async def send(
        self,
        message: discord.Message,
        destination: typing.Union[
            discord.TextChannel, discord.DMChannel, discord.User, discord.Member
        ] = None,
        from_mod: bool = False,
        note: bool = False,
        anonymous: bool = False,
    ) -> None:

        self.bot.loop.create_task(
            self._restart_close_timer()
        )  # Start or restart thread auto close

        if self.close_task is not None:
            # cancel closing if a thread message is sent.
            self.bot.loop.create_task(self.cancel_closure())
            self.bot.loop.create_task(
                self.channel.send(
                    embed=discord.Embed(
                        color=discord.Color.red(),
                        description="Scheduled close has been cancelled.",
                    )
                )
            )

        if not self.ready:
            await self.wait_until_ready()

        if not from_mod and not note:
            self.bot.loop.create_task(self.bot.api.append_log(message, self.channel.id))

        destination = destination or self.channel

        author = message.author

        embed = discord.Embed(description=message.content, timestamp=message.created_at)

        system_avatar_url = (
            "https://discordapp.com/assets/f78426a064bc9dd24847519259bc42af.png"
        )

        if not note:
            if (
                anonymous
                and from_mod
                and not isinstance(destination, discord.TextChannel)
            ):
                # Anonymously sending to the user.
                tag = self.bot.config["mod_tag"]
                if tag is None:
                    tag = str(message.author.top_role)
                name = self.bot.config["anon_username"]
                if name is None:
                    name = tag
                avatar_url = self.bot.config["anon_avatar_url"]
                if avatar_url is None:
                    avatar_url = self.bot.guild.icon_url
            else:
                # Normal message
                name = str(author)
                avatar_url = author.avatar_url

            embed.set_author(name=name, icon_url=avatar_url, url=message.jump_url)
        else:
            # Special note messages
            embed.set_author(
                name=f"Note ({author.name})",
                icon_url=system_avatar_url,
                url=message.jump_url,
            )

        delete_message = not bool(message.attachments)

        ext = [(a.url, a.filename) for a in message.attachments]

        images = []
        attachments = []
        for attachment in ext:
            if is_image_url(attachment[0]):
                images.append(attachment)
            else:
                attachments.append(attachment)

        image_urls = re.findall(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            message.content,
        )

        image_urls = [(url, None) for url in image_urls if is_image_url(url)]
        images.extend(image_urls)

        embedded_image = False

        prioritize_uploads = any(i[1] is not None for i in images)

        additional_images = []
        additional_count = 1

        for url, filename in images:
            if not prioritize_uploads or (
                is_image_url(url) and not embedded_image and filename
            ):
                embed.set_image(url=url)
                if filename:
                    embed.add_field(name="Image", value=f"[{filename}]({url})")
                embedded_image = True
            elif filename is not None:
                if note:
                    color = discord.Color.blurple()
                elif from_mod:
                    color = self.bot.mod_color
                else:
                    color = self.bot.recipient_color

                img_embed = discord.Embed(color=color)
                img_embed.set_image(url=url)
                img_embed.title = filename
                img_embed.url = url
                img_embed.set_footer(
                    text=f"Additional Image Upload ({additional_count})"
                )
                img_embed.timestamp = message.created_at
                additional_images.append(destination.send(embed=img_embed))
                additional_count += 1

        file_upload_count = 1

        for url, filename in attachments:
            embed.add_field(
                name=f"File upload ({file_upload_count})", value=f"[{filename}]({url})"
            )
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
                    mod_tag = str(message.author.top_role)
                embed.set_footer(text=mod_tag)  # Normal messages
            else:
                embed.set_footer(text=self.bot.config["anon_tag"])
        elif note:
            embed.colour = discord.Color.blurple()
        else:
            embed.set_footer(text=f"Message ID: {message.id}")
            embed.colour = self.bot.recipient_color

        try:
            await destination.trigger_typing()
        except discord.NotFound:
            logger.warning("Channel not found.", exc_info=True)
            return

        if not from_mod and not note:
            mentions = self.get_notifications()
        else:
            mentions = None

        msg = await destination.send(mentions, embed=embed)

        if additional_images:
            self.ready = False
            await asyncio.gather(*additional_images)
            self.ready = True

        if delete_message:
            self.bot.loop.create_task(ignore(message.delete()))

        return msg

    def get_notifications(self) -> str:
        key = str(self.id)

        mentions = []
        mentions.extend(self.bot.config["subscriptions"].get(key, []))

        if key in self.bot.config["notification_squad"]:
            mentions.extend(self.bot.config["notification_squad"][key])
            self.bot.config["notification_squad"].pop(key)
            self.bot.loop.create_task(self.bot.config.update())

        return " ".join(mentions)


class ThreadManager:
    """Class that handles storing, finding and creating Modmail threads."""

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}

    async def populate_cache(self) -> None:
        for channel in self.bot.modmail_guild.text_channels:
            if (
                channel.category != self.bot.main_category
                and not self.bot.using_multiple_server_setup
            ):
                continue
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
    ) -> Thread:
        """Finds a thread from cache or from discord channel topics."""
        if recipient is None and channel is not None:
            thread = self._find_from_channel(channel)
            if thread is None:
                user_id, thread = next(
                    ((k, v) for k, v in self.cache.items() if v.channel == channel),
                    (-1, None),
                )
                if thread is not None:
                    logger.debug("Found thread with tempered ID.")
                    await channel.edit(topic=f"User ID: {user_id}")
            return thread

        thread = None

        if recipient:
            recipient_id = recipient.id

        try:
            thread = self.cache[recipient_id]
            if not thread.channel or not self.bot.get_channel(thread.channel.id):
                self.bot.loop.create_task(
                    thread.close(
                        closer=self.bot.user, silent=True, delete_channel=False
                    )
                )
                thread = None
        except KeyError:
            channel = discord.utils.get(
                self.bot.modmail_guild.text_channels, topic=f"User ID: {recipient_id}"
            )
            if channel:
                thread = Thread(self, recipient or recipient_id, channel)
                self.cache[recipient_id] = thread
                thread.ready = True
        return thread

    def _find_from_channel(self, channel):
        """
        Tries to find a thread from a channel channel topic,
        if channel topic doesnt exist for some reason, falls back to
        searching channel history for genesis embed and
        extracts user_id from that.
        """
        user_id = -1

        if channel.topic:
            user_id = match_user_id(channel.topic)

        if user_id != -1:
            if user_id in self.cache:
                return self.cache[user_id]

            recipient = self.bot.get_user(user_id)
            if recipient is None:
                self.cache[user_id] = thread = Thread(self, user_id, channel)
            else:
                self.cache[user_id] = thread = Thread(self, recipient, channel)
            thread.ready = True

            return thread
        return None

    def create(
        self,
        recipient: typing.Union[discord.Member, discord.User],
        *,
        creator: typing.Union[discord.Member, discord.User] = None,
        category: discord.CategoryChannel = None,
    ) -> Thread:
        """Creates a Modmail thread"""
        # create thread immediately so messages can be processed
        thread = Thread(self, recipient)
        self.cache[recipient.id] = thread

        # Schedule thread setup for later
        self.bot.loop.create_task(thread.setup(creator=creator, category=category))
        return thread

    async def find_or_create(self, recipient) -> Thread:
        return await self.find(recipient=recipient) or self.create(recipient)

    def format_channel_name(self, author):
        """Sanitises a username for use with text channel names"""
        name = author.name.lower()
        new_name = (
            "".join(l for l in name if l not in string.punctuation and l.isprintable())
            or "null"
        )
        new_name += f"-{author.discriminator}"

        counter = 1
        while new_name in [c.name for c in self.bot.modmail_guild.text_channels]:
            new_name += f"-{counter}"  # two channels with same name

        return new_name
