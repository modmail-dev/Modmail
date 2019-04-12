import asyncio
import logging
import re
import string
import typing
from datetime import datetime, timedelta

import discord
from discord.ext.commands import UserInputError, CommandError

from core.models import Bot, ThreadManagerABC, ThreadABC
from core.utils import is_image_url, days, match_user_id
from core.utils import truncate, ignore, error


logger = logging.getLogger('Modmail')


class Thread(ThreadABC):
    """Represents a discord Modmail thread"""

    def __init__(self, manager: 'ThreadManager',
                 recipient: typing.Union[discord.Member, discord.User, int],
                 channel: typing.Union[discord.DMChannel,
                                       discord.TextChannel] = None):
        self.manager = manager
        self.bot = manager.bot
        if isinstance(recipient, int):
            self._id = recipient
            self._recipient = None
        else:
            if recipient.bot:
                raise CommandError('Recipient cannot be a bot.')
            self._id = recipient.id
            self._recipient = recipient
        self._channel = channel
        self._ready_event = asyncio.Event()
        self._close_task = None

    def __repr__(self):
        return (f'Thread(recipient="{self.recipient or self.id}", '
                f'channel={self.channel.id})')

    async def wait_until_ready(self):
        """Blocks execution until the thread is fully set up."""
        await self._ready_event.wait()

    @property
    def id(self):
        return self._id

    @property
    def close_task(self):
        return self._close_task

    @close_task.setter
    def close_task(self, val):
        self._close_task = val

    @property
    def channel(self):
        return self._channel

    @property
    def recipient(self):
        return self._recipient

    @property
    def ready(self):
        return self._ready_event.is_set()

    @ready.setter
    def ready(self, flag):
        if flag:
            self._ready_event.set()
        else:
            self._ready_event.clear()

    async def setup(self, *, creator=None, category=None):
        """Create the thread channel and other io related initialisation tasks"""

        recipient = self.recipient

        # in case it creates a channel outside of category
        overwrites = {
            self.bot.modmail_guild.default_role:
                discord.PermissionOverwrite(read_messages=False)
        }

        category = category or self.bot.main_category

        if category is not None:
            overwrites = None

        channel = await self.bot.modmail_guild.create_text_channel(
            name=self.manager._format_channel_name(recipient),
            category=category,
            overwrites=overwrites,
            reason='Creating a thread channel'
        )

        self._channel = channel

        try:
            log_url, log_data = await asyncio.gather(
                self.bot.api.create_log_entry(recipient, channel,
                                            creator or recipient),
                self.bot.api.get_user_logs(recipient.id)
            )

            log_count = sum(1 for log in log_data if not log['open'])
        except: # Something went wrong with database?
            log_url = log_count = None
            # ensure core functionality still works

        info_embed = self.manager._format_info_embed(recipient, log_url,
                                                     log_count,
                                                     discord.Color.green())

        topic = f'User ID: {recipient.id}'
        if creator:
            mention = None
        else:
            mention = self.bot.config.get('mention', '@here')

        async def send_info_embed():
            try:
                msg = await channel.send(mention, embed=info_embed)
                await msg.pin()
            except:
                pass

        await channel.edit(topic=topic)
        self.bot.loop.create_task(send_info_embed())

        self.ready = True

        # Once thread is ready, tell the recipient.
        thread_creation_response = self.bot.config.get(
            'thread_creation_response',
            'The staff team will get back to you as soon as possible.'
        )

        embed = discord.Embed(
            color=self.bot.mod_color,
            description=thread_creation_response,
            timestamp=channel.created_at,
        )

        footer = 'Your message has been sent'
        if not self.bot.config.get('disable_recipient_thread_close'):
            footer = 'Click the lock to close the thread'

        footer = self.bot.config.get('thread_creation_footer', footer)
        embed.set_footer(text=footer, icon_url=self.bot.guild.icon_url)
        embed.title = self.bot.config.get('thread_creation_title', 'Thread Created')

        if creator is None:
            msg = await recipient.send(embed=embed)
            if not self.bot.config.get('disable_recipient_thread_close'):
                close_emoji = self.bot.config.get('close_emoji', '🔒')
                close_emoji = await self.bot.convert_emoji(close_emoji)
                await msg.add_reaction(close_emoji) 

    def _close_after(self, closer, silent, delete_channel, message):
        return self.bot.loop.create_task(
            self._close(closer, silent, delete_channel, message, True)
        )

    async def close(self, *, closer, after=0, silent=False,
                    delete_channel=True, message=None):
        """Close a thread now or after a set time in seconds"""

        # restarts the after timer
        await self.cancel_closure()

        if after > 0:
            # TODO: Add somewhere to clean up broken closures
            #  (when channel is already deleted)
            await self.bot.config.update()
            now = datetime.utcnow()
            items = {
                # 'initiation_time': now.isoformat(),
                'time': (now + timedelta(seconds=after)).isoformat(),
                'closer_id': closer.id,
                'silent': silent,
                'delete_channel': delete_channel,
                'message': message
            }
            self.bot.config.closures[str(self.id)] = items
            await self.bot.config.update()

            self.close_task = self.bot.loop.call_later(
                after, self._close_after, closer,
                silent, delete_channel, message
            )
        else:
            await self._close(closer, silent, delete_channel, message)

    async def _close(self, closer, silent=False, delete_channel=True,
                     message=None, scheduled=False):
        del self.manager.cache[self.id]

        await self.cancel_closure()

        if str(self.id) in self.bot.config.subscriptions:
            del self.bot.config.subscriptions[str(self.id)]

        # Logging
        log_data = await self.bot.api.post_log(self.channel.id, {
            'open': False,
            'closed_at': str(datetime.utcnow()),
            'close_message': message if not silent else None,
            'closer': {
                'id': str(closer.id),
                'name': closer.name,
                'discriminator': closer.discriminator,
                'avatar_url': closer.avatar_url,
                'mod': True
            }
        })

        if log_data is not None and isinstance(log_data, dict):
            if self.bot.self_hosted:
                log_url = f"{self.bot.config.log_url.strip('/')}/" \
                    f"logs/{log_data['key']}"
            else:
                log_url = f"https://logs.modmail.tk/{log_data['key']}"

            if log_data['messages']:
                content = str(log_data['messages'][0]['content'])
                sneak_peak = content.replace('\n', '')
            else:
                sneak_peak = 'No content'

            desc = f"[`{log_data['key']}`]({log_url}): "
            desc += truncate(sneak_peak, max=75 - 13)
        else:
            desc = "Could not resolve log url."
            log_url = None

        embed = discord.Embed(description=desc, color=discord.Color.red())

        if self.recipient is not None:
            user = f"{self.recipient} (`{self.id}`)"
        else:
            user = f'`{self.id}`'
        
        if self.id == closer.id:
            _closer = 'the Recipient'
        else:
            _closer = f'{closer} ({closer.id})'

        embed.title = user

        event = 'Thread Closed as Scheduled' if scheduled else 'Thread Closed'
        # embed.set_author(name=f'Event: {event}', url=log_url)
        embed.set_footer(text=f'{event} by {_closer}')
        embed.timestamp = datetime.utcnow()

        tasks = [
            self.bot.config.update()
        ]
        
        try:
            tasks.append(self.bot.log_channel.send(embed=embed))
        except (ValueError, AttributeError):
            pass

        # Thread closed message

        embed = discord.Embed(title=self.bot.config.get('thread_close_title', 'Thread Closed'),
                              color=discord.Color.red(),
                              timestamp=datetime.utcnow())

        if not message:
            if self.id == closer.id:
                message = self.bot.config.get(
                    'thread_self_close_response', 
                    'You have closed this Modmail thread.'
                    )
            else:
                message = self.bot.config.get(
                    'thread_close_response',
                    '{closer.mention} has closed this Modmail thread.'
                    )
            
        message = message.format(closer=closer, loglink=log_url, logkey=log_data['key'])

        embed.description = message
        footer = self.bot.config.get('thread_close_footer', 'Replying will create a new thread')
        embed.set_footer(text=footer,
                         icon_url=self.bot.guild.icon_url)

        if not silent and self.recipient is not None:
            tasks.append(self.recipient.send(embed=embed))

        if delete_channel:
            tasks.append(self.channel.delete())

        await asyncio.gather(*tasks)

    async def cancel_closure(self):
        if self.close_task is not None:
            self.close_task.cancel()
            self.close_task = None

        to_update = self.bot.config.closures.pop(str(self.id), None)
        if to_update is not None:
            await self.bot.config.update()

    @staticmethod
    async def _edit_thread_message(channel, message_id, message):
        async for msg in channel.history():
            if not msg.embeds:
                continue
            embed = msg.embeds[0]
            if embed and embed.author and embed.author.url:
                if str(message_id) == str(embed.author.url).split('/')[-1]:
                    embed.description = message
                    await msg.edit(embed=embed)
                    break

    async def edit_message(self, message_id, message):
        await asyncio.gather(
            self._edit_thread_message(self.recipient, message_id, message),
            self._edit_thread_message(self.channel, message_id, message)
        )

    async def note(self, message):
        if not message.content and not message.attachments:
            raise UserInputError

        await asyncio.gather(
            self.bot.api.append_log(message,
                                    self.channel.id,
                                    type_='system'),
            self.send(message, self.channel, note=True)
        )

    async def reply(self, message, anonymous=False):
        if not message.content and not message.attachments:
            raise UserInputError
        if all(not g.get_member(self.id) for g in self.bot.guilds):
            return await message.channel.send(
                embed=discord.Embed(
                    color=discord.Color.red(),
                    description='Your message could not be delivered since '
                                'the recipient shares no servers with the bot.'
                ))

        tasks = []

        try:
            await self.send(message,
                            destination=self.recipient,
                            from_mod=True,
                            anonymous=anonymous)
        except Exception:
            logger.info(error('Message delivery failed:'), exc_info=True)
            tasks.append(message.channel.send(
                embed=discord.Embed(
                    color=discord.Color.red(),
                    description='Your message could not be delivered as '
                                'the recipient is only accepting direct '
                                'messages from friends, or the bot was '
                                'blocked by the recipient.'
                )
            ))
        else:
            # Send the same thing in the thread channel.
            tasks.append(
                self.send(message,
                          destination=self.channel,
                          from_mod=True,
                          anonymous=anonymous)
            )

            tasks.append(
                self.bot.api.append_log(message,
                                        self.channel.id,
                                        type_='anonymous' if anonymous else 'thread_message'
                                        ))

        if self.close_task is not None:
            # Cancel closing if a thread message is sent.
            await self.cancel_closure()
            tasks.append(
                self.channel.send(
                    embed=discord.Embed(
                        color=discord.Color.red(),
                        description='Scheduled close has been cancelled.'
                    )
                )
            )

        await asyncio.gather(*tasks)

    async def send(self, message, destination=None,
                   from_mod=False, note=False, anonymous=False):
        if self.close_task is not None:
            # cancel closing if a thread message is sent.
            self.bot.loop.create_task(
                self.cancel_closure()
            )
            self.bot.loop.create_task(
                self.channel.send(embed=discord.Embed(
                    color=discord.Color.red(),
                    description='Scheduled close has been cancelled.'
                ))
            )

        if not self.ready:
            await self.wait_until_ready()

        if not from_mod and not note:
            self.bot.loop.create_task(
                self.bot.api.append_log(message, self.channel.id)
            )

        destination = destination or self.channel

        author = message.author

        embed = discord.Embed(
            description=message.content,
            timestamp=message.created_at
        )

        system_avatar_url = 'https://discordapp.com/assets/' \
                            'f78426a064bc9dd24847519259bc42af.png'

        if not note:
            if anonymous and from_mod and \
                    not isinstance(destination, discord.TextChannel):
                # Anonymously sending to the user.
                tag = self.bot.config.get('mod_tag',
                                          str(message.author.top_role))
                name = self.bot.config.get('anon_username', tag)
                avatar_url = self.bot.config.get('anon_avatar_url',
                                                 self.bot.guild.icon_url)
            else:
                # Normal message
                name = str(author)
                avatar_url = author.avatar_url

            embed.set_author(name=name,
                             icon_url=avatar_url,
                             url=message.jump_url)
        else:
            # Special note messages
            embed.set_author(name=f'Note ({author.name})',
                             icon_url=system_avatar_url,
                             url=message.jump_url)

        delete_message = not bool(message.attachments)

        attachments = [(a.url, a.filename) for a in message.attachments]

        images = [x for x in attachments if is_image_url(*x)]
        attachments = [x for x in attachments if not is_image_url(*x)]

        image_links = [
            (link, None) for link in re.findall(r'(https?://[^\s]+)',
                                                message.content)
        ]
        image_links = [x for x in image_links if is_image_url(*x)]
        images.extend(image_links)

        embedded_image = False

        prioritize_uploads = any(i[1] is not None for i in images)

        additional_images = []
        additional_count = 1

        for att in images:
            if not prioritize_uploads or (
                    is_image_url(*att) and not
                    embedded_image and
                    att[1]
            ):
                embed.set_image(url=att[0])
                if att[1]:
                    embed.add_field(name='Image', value=f'[**{att[1]}**]({att[0]})')
                embedded_image = True
            elif att[1] is not None:
                if note:
                    color = discord.Color.blurple()
                elif from_mod:
                    color = self.bot.mod_color
                else:
                    color = self.bot.recipient_color

                img_embed = discord.Embed(color=color)
                img_embed.set_image(url=att[0])
                img_embed.title = att[1]
                img_embed.url = att[0]
                img_embed.set_footer(
                    text=f'Additional Image Upload ({additional_count})'
                )
                img_embed.timestamp = message.created_at
                additional_images.append(destination.send(embed=img_embed))
                additional_count += 1

        file_upload_count = 1

        for att in attachments:
            embed.add_field(name=f'File upload ({file_upload_count})',
                            value=f'[{att[1]}]({att[0]})')
            file_upload_count += 1

        if from_mod:
            # noinspection PyUnresolvedReferences,PyDunderSlots
            embed.color = self.bot.mod_color  # pylint: disable=E0237
            # Anonymous reply sent in thread channel
            if anonymous and isinstance(destination, discord.TextChannel):
                embed.set_footer(text='Anonymous Reply')
            # Normal messages
            elif not anonymous:
                tag = self.bot.config.get('mod_tag',
                                          str(message.author.top_role))
                embed.set_footer(text=tag)  # Normal messages
            else:
                embed.set_footer(
                    text=self.bot.config.get('anon_tag', 'Response')
                )
        elif note:
            # noinspection PyUnresolvedReferences,PyDunderSlots
            embed.color = discord.Color.blurple()  # pylint: disable=E0237
        else:
            embed.set_footer(text=f'Recipient')
            # noinspection PyUnresolvedReferences,PyDunderSlots
            embed.color = self.bot.recipient_color  # pylint: disable=E0237

        await destination.trigger_typing()

        if not from_mod:
            mentions = self.get_notifications()
        else:
            mentions = None

        await destination.send(mentions, embed=embed)
        if additional_images:
            self.ready = False
            await asyncio.gather(*additional_images)
            self.ready = True

        if delete_message:
            self.bot.loop.create_task(ignore(message.delete()))

    def get_notifications(self):
        config = self.bot.config
        key = str(self.id)

        mentions = []
        mentions.extend(config['subscriptions'].get(key, []))

        if key in config['notification_squad']:
            mentions.extend(config['notification_squad'][key])
            del config['notification_squad'][key]
            self.bot.loop.create_task(config.update())

        return ' '.join(mentions)


class ThreadManager(ThreadManagerABC):
    """Class that handles storing, finding and creating Modmail threads."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.cache = {}

    async def populate_cache(self):
        for channel in self.bot.modmail_guild.text_channels:
            if channel.category != self.bot.main_category and not \
                    self.bot.using_multiple_server_setup:
                continue
            await self.find(channel=channel)

    def __len__(self):
        return len(self.cache)

    def __iter__(self):
        return iter(self.cache.values())

    def __getitem__(self, item):
        return self.cache[item]

    async def find(self, *, recipient=None, channel=None):
        """Finds a thread from cache or from discord channel topics."""
        if recipient is None and channel is not None:
            return await self._find_from_channel(channel)

        thread = None
        try:
            thread = self.cache[recipient.id]
        except KeyError:
            channel = discord.utils.get(
                self.bot.modmail_guild.text_channels,
                topic=f'User ID: {recipient.id}'
            )
            if channel:
                thread = Thread(self, recipient, channel)
                self.cache[recipient.id] = thread
                thread.ready = True
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

        # BUG: When discord fails to create channel topic.
        # search through message history
        elif channel.topic is None:
            try:
                async for message in channel.history(limit=100):
                    if message.embeds:
                        embed = message.embeds[0]
                        if embed.footer.text:
                            user_id = match_user_id(embed.footer.text)
                            if user_id != -1:
                                break
            except discord.NotFound:
                # When the channel's deleted.
                pass

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

    def create(self, recipient, *, creator=None, category=None):
        """Creates a Modmail thread"""
        # create thread immediately so messages can be processed
        thread = Thread(self, recipient)
        self.cache[recipient.id] = thread

        # Schedule thread setup for later
        self.bot.loop.create_task(thread.setup(
            creator=creator,
            category=category
        ))
        return thread

    async def find_or_create(self, recipient):
        return await self.find(recipient=recipient) or self.create(recipient)

    def _format_channel_name(self, author):
        """Sanitises a username for use with text channel names"""
        name = author.name.lower()
        allowed = string.ascii_letters + string.digits + '-'
        new_name = ''.join(l for l in name if l in allowed) or 'null'
        new_name += f'-{author.discriminator}'

        while new_name in [c.name for c in
                           self.bot.modmail_guild.text_channels]:
            new_name += '-x'  # two channels with same name

        return new_name

    def _format_info_embed(self, user, log_url, log_count, color):
        """Get information about a member of a server
        supports users from the guild or not."""
        member = self.bot.guild.get_member(user.id)
        avi = user.avatar_url
        time = datetime.utcnow()

        # key = log_url.split('/')[-1]

        role_names = ''
        if member:
            sep_server = self.bot.using_multiple_server_setup
            separator = ', ' if sep_server else ' '

            roles = []

            for role in sorted(member.roles, key=lambda r: r.position):
                if role.name == '@everyone':
                    continue

                fmt = role.name if sep_server else role.mention
                roles.append(fmt)

                if len(separator.join(roles)) > 1024:
                    roles.append('...')
                    while len(separator.join(roles)) > 1024:
                        roles.pop(-2)
                    break

            role_names = separator.join(roles)

        embed = discord.Embed(color=color,
                              description=user.mention,
                              timestamp=time)

        created = str((time - user.created_at).days)
        # if not role_names:
        #     embed.add_field(name='Mention', value=user.mention)
        # embed.add_field(name='Registered', value=created + days(created))
        embed.description += f' was created {days(created)}'

        footer = 'User ID: ' + str(user.id)
        embed.set_footer(text=footer)
        embed.set_author(name=str(user), icon_url=avi, url=log_url)
        # embed.set_thumbnail(url=avi)

        if member:
            joined = str((time - member.joined_at).days)
            # embed.add_field(name='Joined', value=joined + days(joined))
            embed.description += f', joined {days(joined)}'

            if member.nick:
                embed.add_field(name='Nickname',
                                value=member.nick,
                                inline=True)
            if role_names:
                embed.add_field(name='Roles',
                                value=role_names,
                                inline=True)
        else:
            embed.set_footer(text=f'{footer} | Note: this member '
                                  'is not part of this server.')

        if log_count:
            # embed.add_field(name='Past logs', value=f'{log_count}')
            thread = 'thread' if log_count == 1 else 'threads'
            embed.description += f" with **{log_count}** past {thread}."
        else:
            embed.description += '.'

        return embed
