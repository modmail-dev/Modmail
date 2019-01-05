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

    def __repr__(self):
        return f'Thread(recipient="{self.recipient}", channel={self.channel.id})'

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

    def close(self):
        del self.manager.cache[self.id]
        return self.channel.delete()

    async def _edit_thread_message(self, channel, message_id, message):
        async for msg in channel.history():
            if not msg.embeds:
                continue
            embed = msg.embeds[0]
            if embed and embed.author and embed.author.url:
                if str(message_id) == str(embed.author.url).split('/')[-1]:
                    if ' - (Edited)' not in embed.footer.text:
                        embed.set_footer(text=embed.footer.text + ' - (Edited)')
                    embed.description = message
                    await msg.edit(embed=embed)
                    break

    def edit_message(self, message_id, message):
        return asyncio.gather(
            self._edit_thread_message(self.recipient, message_id, message),
            self._edit_thread_message(self.channel, message_id, message)
        )

    async def reply(self, message):
        if not message.content and not message.attachments:
            raise commands.UserInputError
        if not self.recipient:
            return await message.channel.send('This user does not share any servers with the bot and is thus unreachable.')
        await asyncio.gather(
            self.send(message, self.channel, from_mod=True),  # in thread channel
            self.send(message, self.recipient, from_mod=True)  # to user
        )

    async def send(self, message, destination=None, from_mod=False, delete_message=True):
        if not self.ready:
            await self.wait_until_ready()

        destination = destination or self.channel
        if from_mod and not isinstance(destination, discord.User):
            asyncio.create_task(self.bot.modmail_api.append_log(message))
        elif not from_mod:
            asyncio.create_task(self.bot.modmail_api.append_log(message, destination.id))

        author = message.author

        em = discord.Embed(
            description=message.content,
            timestamp=message.created_at
        )

        em.set_author(name=str(author), icon_url=author.avatar_url, url=message.jump_url)  # store message id in hidden url

        image_types = ['.png', '.jpg', '.gif', '.jpeg', '.webp']
        is_image_url = lambda u: any(urlparse(u.lower()).path.endswith(x) for x in image_types)

        delete_message = not bool(message.attachments)
        attachments = list(filter(lambda a: not is_image_url(a.url), message.attachments))

        image_urls = [a.url for a in message.attachments]
        image_urls.extend(re.findall(r'(https?://[^\s]+)', message.content))
        image_urls = list(filter(is_image_url, image_urls))

        if image_urls:
            em.set_image(url=image_urls[0])

        if attachments:
            att = attachments[0]
            em.add_field(name='File Attachment', value=f'[{att.filename}]({att.url})')

        if from_mod:
            em.color = discord.Color.green()
            em.set_footer(text=f'Moderator')
        else:
            em.color = discord.Color.gold()
            em.set_footer(text=f'User')

        await destination.trigger_typing()
        await destination.send(embed=em)

        if delete_message:
            try:
                await message.delete()
            except:
                pass


class ThreadManager:
    """Class that handles storing, finding and creating modmail threads."""

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}

    async def populate_cache(self):
        for channel in self.bot.modmail_guild.text_channels:
            if not self.bot.using_multiple_server_setup and channel.category != self.main_category:
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
        try:
            thread = self.cache[recipient.id]
        except KeyError:
            channel = discord.utils.get(
                self.bot.modmail_guild.text_channels,
                topic=f'User ID: {recipient.id}'
            )
            if not channel:
                thread = None
            else:
                self.cache[recipient.id] = thread = Thread(self, recipient)
                thread.channel = channel
                thread.ready = True
        finally:
            return thread

    async def _find_from_channel(self, channel):
        """
        Tries to find a thread from a channel channel topic,
        if channel topic doesnt exist for some reason, falls back to
        searching channel history for genesis embed and extracts user_id fron that.
        """
        user_id = None

        if channel.topic and 'User ID: ' in channel.topic:
            user_id = int(re.findall(r'\d+', channel.topic)[0])

        # BUG: When discord fails to create channel topic. search through message history
        elif channel.topic is None:
            async for message in channel.history(limit=50):
                if message.embeds:
                    em = message.embeds[0]
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

    async def create(self, recipient, *, creator=None):
        """Creates a modmail thread"""

        em = discord.Embed(
            title='Thread started' if creator else 'Thanks for the message!',
            description='The moderation team will get back to you as soon as possible!',
            color=discord.Color.green()
        )

        if creator is None:
            asyncio.create_task(recipient.send(embed=em))

        self.cache[recipient.id] = thread = Thread(self, recipient)

        channel = await self.bot.modmail_guild.create_text_channel(
            name=self._format_channel_name(recipient),
            category=self.bot.main_category
        )

        thread.channel = channel

        log_url, log_data = await asyncio.gather(
            self.bot.modmail_api.get_log_url(recipient, channel, creator or recipient),
            self.bot.modmail_api.get_user_logs(recipient.id)
            # self.get_dominant_color(recipient.avatar_url)
        )

        log_count = sum(1 for log in log_data if not log['open'])
        info_embed = self._format_info_embed(recipient, creator, log_url, log_count, discord.Color.green())

        topic = f'User ID: {recipient.id}'
        mention = self.bot.config.get('mention', '@here') if not creator else None

        _, msg = await asyncio.gather(
            channel.edit(topic=topic),
            channel.send(mention, embed=info_embed)
        )

        thread.ready = True

        await msg.pin()

        return thread

    async def find_or_create(self, recipient):
        return await self.find(recipient=recipient) or await self.create(recipient)

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
        except Exception:
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

        while new_name in [c.name for c in self.bot.modmail_guild.text_channels]:
            new_name += '-x'  # two channels with same name

        return new_name

    def _format_info_embed(self, user, creator, log_url, log_count, dc):
        """Get information about a member of a server
        supports users from the guild or not."""
        member = self.bot.guild.get_member(user.id)
        avi = user.avatar_url
        time = datetime.datetime.utcnow()
        desc = f'{creator.mention} has created a thread with {user.mention}' if creator else f'{user.mention} has started a thread'
        key = log_url.split('/')[-1]
        desc = f'{desc} [`{key}`]({log_url})'

        if member:
            seperate_server = self.bot.guild != self.bot.modmail_guild
            roles = sorted(member.roles, key=lambda c: c.position)
            rolenames = ' '.join(r.mention if not seperate_server else r.name for r in roles if r.name != "@everyone")

        em = discord.Embed(colour=dc, description=desc, timestamp=time)

        days = lambda d: (' day ago.' if d == '1' else ' days ago.')

        created = str((time - user.created_at).days)
        # em.add_field(name='Mention', value=user.mention)
        em.add_field(name='Registered', value=created + days(created))
        footer = 'User ID: ' + str(user.id)
        em.set_footer(text=footer)
        em.set_author(name=str(user), icon_url=avi)
        em.set_thumbnail(url=avi)

        if member:
            if log_count:
                em.add_field(name='Past logs', value=f'{log_count}')
            joined = str((time - member.joined_at).days)
            em.add_field(name='Joined', value=joined + days(joined))
            if member.nick:
                em.add_field(name='Nickname', value=member.nick, inline=True)
            if rolenames:
                em.add_field(name='Roles', value=rolenames, inline=False)
        else:
            em.set_footer(text=footer + ' | Note: this member is not part of this server.')

        return em
