from urllib.parse import urlparse
import traceback
import datetime
import asyncio
import string
import re
import io

import discord
from discord.ext import commands

from core.decorators import asyncexecutor
from colorthief import ColorThief


class Thread:
    """Represents a discord modmail thread"""

    def __init__(self, manager, recipient):
        self.manager = manager
        self.bot = manager.bot
        self.id = recipient.id if recipient else None
        self.recipient = recipient
        self.channel = None
        self.ready_event = asyncio.Event()
        self.close_task = None

    def __repr__(self):
        return f'Thread(recipient="{self.recipient}", ' \
               f'channel={self.channel.id})'

    def wait_until_ready(self):
        """Blocks execution until the thread is fully set up."""
        return self.ready_event.wait()

    @property
    def ready(self):
        return self.ready_event.is_set()

    @ready.setter
    def ready(self, flag):
        if flag is True:
            self.ready_event.set()
    
    def _close_after(self, closer, silent, delete_channel, message):
        return self.bot.loop.create_task(
            self._close(closer, silent, delete_channel, message, True))

    async def close(self, *, closer, after=0, silent=False,
                    delete_channel=True, message=None):
        """Close a thread now or after a set time in seconds"""

        # restarts the after timer
        await self.cancel_closure()

        if after > 0:
            # TODO: Add somewhere to clean up broken closures
            #  (when channel is already deleted)
            await self.bot.config.update()
            now = datetime.datetime.utcnow()
            items = {
                # 'initiation_time': now.isoformat(),
                'time': (now + datetime.timedelta(seconds=after)).isoformat(),
                'closer_id': closer.id,
                'silent': silent,
                'delete_channel': delete_channel,
                'message': message
            }
            self.bot.config.closures[str(self.id)] = items
            await self.bot.config.update()

            self.close_task = self.bot.loop.call_later(
                after, self._close_after, closer,
                silent, delete_channel, message)
            return

        return await self._close(closer, silent, delete_channel, message)

    async def _close(self, closer, silent=False, delete_channel=True,
                     message=None, scheduled=False):
        del self.manager.cache[self.id]

        await self.cancel_closure()

        if str(self.id) in self.bot.config.subscriptions:
            del self.bot.config.subscriptions[str(self.id)]

        # Logging
        log_data = await self.bot.modmail_api.post_log(self.channel.id, {
            'open': False,
            'closed_at': str(datetime.datetime.utcnow()),
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
            if self.bot.selfhosted:
                log_url = f"{self.bot.config.log_url.strip('/')}/logs/{log_data['key']}"
            else:
                log_url = f"https://logs.modmail.tk/{log_data['key']}"

            user = self.recipient.mention if self.recipient else f'`{self.id}`'

            if log_data['messages']:
                msg = str(log_data['messages'][0]['content'])
                sneak_peak = msg if len(msg) < 50 else msg[:48] + '...'
            else:
                sneak_peak = 'No content'
            
            desc = f"{user} [`{log_data['key']}`]({log_url}): {sneak_peak}"
        else:
            desc = "Could not resolve log url."

        em = discord.Embed(description=desc, color=discord.Color.red())

        event = 'Thread Closed as Scheduled' if scheduled else 'Thread Closed'
        # em.set_author(name=f'Event: {event}', url=log_url)
        em.set_footer(text=f'{event} by {closer} ({closer.id})')
        em.timestamp = datetime.datetime.utcnow()

        tasks = [
            self.bot.config.update()
        ]

        if self.bot.log_channel:
            tasks.append(self.bot.log_channel.send(embed=em))

        # Thread closed message 

        em = discord.Embed(title='Thread Closed', color=discord.Color.red())
        em.description = message or \
            f'{closer.mention} has closed this Modmail thread.'
        em.set_footer(text='Replying will create a new thread', icon_url=self.bot.guild.icon_url)
        em.timestamp = datetime.datetime.utcnow()

        if not silent and self.recipient is not None:
            tasks.append(self.recipient.send(embed=em))
        
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

    def edit_message(self, message_id, message):
        return asyncio.gather(
            self._edit_thread_message(self.recipient, message_id, message),
            self._edit_thread_message(self.channel, message_id, message)
        )
    
    async def note(self, message):
        if not message.content and not message.attachments:
            raise commands.UserInputError
            
        await asyncio.gather(
            self.bot.modmail_api.append_log(message, self.channel.id, type='system'),
            self.send(message, self.channel, note=True)
        )

    async def reply(self, message, anonymous=False):
        if not message.content and not message.attachments:
            raise commands.UserInputError
        if all(not g.get_member(self.id) for g in self.bot.guilds):
            return await message.channel.send(
                embed=discord.Embed(
                    color=discord.Color.red(),
                    description='This user shares no servers with '
                                'me and is thus unreachable.'))

        tasks = [
            # in thread channel
            self.send(message, destination=self.channel, from_mod=True, anonymous=anonymous),
            # to user
            self.send(message, destination=self.recipient, from_mod=True, anonymous=anonymous)
            ]
        

        self.bot.loop.create_task(
            self.bot.modmail_api.append_log(message, self.channel.id, type='anonymous' if anonymous else 'thread_message')
            )

        if self.close_task is not None:
            # cancel closing if a thread message is sent.
            await self.cancel_closure()
            tasks.append(self.channel.send(
                embed=discord.Embed(color=discord.Color.red(),
                                    description='Scheduled close has '
                                                'been cancelled.')))

        await asyncio.gather(*tasks)

    async def send(self, message, destination=None, from_mod=False, note=False, anonymous=False):
        if self.close_task is not None:
            # cancel closing if a thread message is sent.
            await self.cancel_closure()
            await self.channel.send(embed=discord.Embed(
                color=discord.Color.red(),
                description='Scheduled close has been cancelled.'))
        
        if not from_mod and not note:
            self.bot.loop.create_task(
                self.bot.modmail_api.append_log(message, self.channel.id)
                )

        if not self.ready:
            await self.wait_until_ready()

        destination = destination or self.channel

        author = message.author

        em = discord.Embed(
            description=message.content,
            timestamp=message.created_at
        )

        system_avatar_url = 'https://discordapp.com/assets/f78426a064bc9dd24847519259bc42af.png'

        # store message id in hidden url
        if not note:

            if anonymous and from_mod and not isinstance(destination, discord.TextChannel):
                # Anonymously sending to the user.
                name = self.bot.config.get('anon_username', self.bot.config.get('mod_tag', 'Moderator'))
                avatar_url = self.bot.config.get('anon_avatar_url', self.bot.guild.icon_url)
            else:
                # Normal message
                name = str(author)
                avatar_url = author.avatar_url

            em.set_author(name=name,
                      icon_url=avatar_url,
                      url=message.jump_url)
        else:
            # Special note messages
            em.set_author(
                name=f'Note ({author.name})',
                icon_url=system_avatar_url,
                url=message.jump_url
            )

        image_types = ['.png', '.jpg', '.gif', '.jpeg', '.webp']

        def is_image_url(u, _):
            return any(urlparse(u.lower()).path.endswith(x)
                       for x in image_types)

        delete_message = not bool(message.attachments)

        attachments = [(a.url, a.filename) for a in message.attachments]
        
        images = [x for x in attachments if is_image_url(*x)]
        attachments = [x for x in attachments if not is_image_url(*x)]

        image_links = [(link, None) for link in
                       re.findall(r'(https?://[^\s]+)', message.content)]
        image_links = [x for x in image_links if is_image_url(*x)]
        images.extend(image_links)

        embedded_image = False

        prioritize_uploads = any(i[1] is not None for i in images)

        additional_count = 1

        for att in images:
            if is_image_url(*att) and not embedded_image and att[1] \
                    if prioritize_uploads else True:
                em.set_image(url=att[0])
                embedded_image = True
            elif att[1] is not None:
                link = f'[{att[1]}]({att[0]})'
                em.add_field(
                    name=f'Additional Image upload ({additional_count})',
                    value=link,
                    inline=False
                )
                additional_count += 1
        
        file_upload_count = 1

        for att in attachments:
            em.add_field(name=f'File upload ({file_upload_count})',
                         value=f'[{att[1]}]({att[0]})')
            file_upload_count += 1

        if from_mod:
            em.color = self.bot.mod_color
            if anonymous and isinstance(destination, discord.TextChannel): # Anonymous reply sent in thread channel
                em.set_footer(text='Anonymous Reply')
            elif not anonymous:
                em.set_footer(text=self.bot.config.get('mod_tag', 'Moderator')) # Normal messages
            else:
                em.set_footer(text=self.bot.config.get('anon_tag', 'Response')) # Anonymous reply sent to user
                
        elif note:
            em.color = discord.Color.blurple()
        else:
            em.set_footer(text=f'Recipient')
            em.color = self.bot.recipient_color

        await destination.trigger_typing()

        if not from_mod:
            mentions = self.get_notifications()
        else:
            mentions = None
            
        await destination.send(mentions, embed=em)

        if delete_message:
            try:
                await message.delete()
            except:
                pass
        
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


class ThreadManager:
    """Class that handles storing, finding and creating Modmail threads."""

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}

    async def populate_cache(self):
        for channel in self.bot.modmail_guild.text_channels:
            if not self.bot.using_multiple_server_setup and \
                    channel.category != self.bot.main_category:
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
                self.cache[recipient.id] = thread = Thread(self, recipient)
                # TODO: Fix this:
                thread.channel = channel
                thread.ready = True
        finally:
            return thread

    async def _find_from_channel(self, channel):
        """
        Tries to find a thread from a channel channel topic,
        if channel topic doesnt exist for some reason, falls back to
        searching channel history for genesis embed and
        extracts user_id from that.
        """
        user_id = None

        if channel.topic and 'User ID: ' in channel.topic:
            user_id = int(re.findall(r'\d+', channel.topic)[0])

        # BUG: When discord fails to create channel topic.
        # search through message history
        elif channel.topic is None:
            async for message in channel.history(limit=50):
                if message.embeds:
                    em = message.embeds[0]
                    # TODO: use re.search instead
                    matches = re.findall(r'User ID: (\d+)', str(em.footer.text))
                    if matches:
                        user_id = int(matches[0])
                        break

        if user_id is not None:
            if user_id in self.cache:
                return self.cache[user_id]

            recipient = self.bot.get_user(user_id)  # this could be None

            self.cache[user_id] = thread = Thread(self, recipient)
            thread.ready = True
            thread.channel = channel
            thread.id = user_id

            return thread

    async def create(self, recipient, *, creator=None, category=None):
        """Creates a Modmail thread"""

        thread_creation_response = self.bot.config.get(
                'thread_creation_response',
                'The moderation team will get back to you as soon as possible!'
            )

        em = discord.Embed(color=self.bot.mod_color)
        em.description = thread_creation_response
        em.set_author(name='Thread Created')
        em.timestamp = datetime.datetime.utcnow()
        em.set_footer(text='Your message has been sent', icon_url=self.bot.guild.icon_url)

        if creator is None:
            self.bot.loop.create_task(recipient.send(embed=em))

        self.cache[recipient.id] = thread = Thread(self, recipient)

        overwrites = { 
            self.bot.modmail_guild.default_role: discord.PermissionOverwrite(read_messages=False) 
            }
        # in case it creates a channel outside of category

        category = category or self.bot.main_category

        if category is not None:
            overwrites = None 

        channel = await self.bot.modmail_guild.create_text_channel(
            name=self._format_channel_name(recipient),
            category=category,
            overwrites=overwrites,
            reason='Creating a thread channel'
        )

        thread.channel = channel

        log_url, log_data = await asyncio.gather(
            self.bot.modmail_api.get_log_url(recipient, channel, creator or recipient),
            self.bot.modmail_api.get_user_logs(recipient.id)
            # self.get_dominant_color(recipient.avatar_url)
        )

        log_count = sum(1 for log in log_data if not log['open'])
        info_embed = self._format_info_embed(recipient, creator,
                                             log_url, log_count,
                                             discord.Color.green())

        topic = f'User ID: {recipient.id}'
        mention = self.bot.config.get('mention', '@here') \
            if not creator else None

        _, msg = await asyncio.gather(
            channel.edit(topic=topic),
            channel.send(mention, embed=info_embed)
        )

        thread.ready = True

        await msg.pin()

        return thread

    async def find_or_create(self, recipient):
        return await self.find(recipient=recipient) or \
               await self.create(recipient)

    @staticmethod
    def valid_image_url(url):
        """Checks if a url leads to an image."""
        types = ['.png', '.jpg', '.gif', '.webp']
        parsed = urlparse(url)
        if any(parsed.path.endswith(i) for i in types):
            return url.replace(parsed.query, 'size=128')
        return False

    @asyncexecutor()
    def _do_get_dc(self, image, quality):
        with io.BytesIO(image) as f:
            return ColorThief(f).get_color(quality=quality)

    async def get_dominant_color(self, url=None, quality=10):
        """
        Returns the dominant color of an image from a url
        (misc)
        """
        url = self.valid_image_url(url)

        if not url:
            raise ValueError('Invalid image url passed.')
        try:
            async with self.bot.session.get(url) as resp:
                image = await resp.read()
                color = await self._do_get_dc(image, quality)
        except:
            traceback.print_exc()
            return discord.Color.blurple()
        else:
            return discord.Color.from_rgb(*color)

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

    def _format_info_embed(self, user, creator, log_url, log_count, dc):
        """Get information about a member of a server
        supports users from the guild or not."""
        member = self.bot.guild.get_member(user.id)
        avi = user.avatar_url
        time = datetime.datetime.utcnow()

        key = log_url.split('/')[-1]

        role_names = ''
        if member:
            separate_server = self.bot.guild != self.bot.modmail_guild
            roles = sorted(member.roles, key=lambda c: c.position)
            if separate_server:
                role_names = ', '.join(r.name for r in roles
                                       if r.name != "@everyone")
            else:
                role_names = ' '.join(r.mention for r in roles
                                      if r.name != "@everyone")

        em = discord.Embed(colour=dc, description=user.mention, timestamp=time)

        def days(d):
            if d == '0':
                return '**today**'
            return f'{d} day ago' if d == '1' else f'{d} days ago'

        created = str((time - user.created_at).days)
        # if not role_names:
        #     em.add_field(name='Mention', value=user.mention)
        # em.add_field(name='Registered', value=created + days(created))
        em.description += f' was created {days(created)}'

        footer = 'User ID: ' + str(user.id)
        em.set_footer(text=footer)
        em.set_author(name=str(user), icon_url=avi, url=log_url)
        # em.set_thumbnail(url=avi)

        if member:
            joined = str((time - member.joined_at).days)
            # em.add_field(name='Joined', value=joined + days(joined))
            em.description += f', joined {days(joined)}'

            if member.nick:
                em.add_field(name='Nickname', value=member.nick, inline=True)
            if role_names:
                em.add_field(name='Roles', value=role_names, inline=True)
        else:
            em.set_footer(
                text=f'{footer} | Note: this member'
                     f' is not part of this server.')

        if log_count:
            # em.add_field(name='Past logs', value=f'{log_count}')
            em.description += f" with **{log_count}** past {'thread' if log_count == 1 else 'threads'}."
        else:
            em.description += '.'

        return em
