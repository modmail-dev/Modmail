import discord
from discord.ext import commands
import asyncio
import functools
import re

class Thread:
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
        '''Blocks execution until the thread is fully set up.'''
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
            if msg.embeds:
                embed = msg.embeds[0]
                if f'Moderator - {message_id}' in embed.footer.text:
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
            raise commands.UserInputError('msg is a required argument.')
        if not self.recipient:
            return await message.channel.send('This user does not share any servers with the bot and is thus unreachable.')
        await asyncio.gather(
            self.send(message, self.channel, from_mod=True), # in thread channel
            self.send(message, self.recipient, from_mod=True) # to user
        )

    async def send(self, message, destination=None, from_mod=False, delete_message=True):
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

        image_types = ['.png', '.jpg', '.gif', '.jpeg', '.webp']
        is_image_url = lambda u: any(urlparse(u).path.endswith(x) for x in image_types)

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
            em.color=discord.Color.green()
            em.set_author(name=str(author), icon_url=author.avatar_url)
            em.set_footer(text=f'Moderator - {message.id}')
        else:
            em.color=discord.Color.gold()
            em.set_author(name=str(author), icon_url=author.avatar_url)
            em.set_footer(text=f'User - {message.id}')

        if not self.ready:
            await self.wait_until_ready()
        
        await destination.trigger_typing()
        await destination.send(embed=em)

        if delete_message:
            try:
                await message.delete()
            except:
                pass

class ThreadManager:
    def __init__(self, bot):
        self.bot = bot 
        self.cache = {}

    def __len__(self):
        return len(self.cache)

    def __iter__(self):
        return iter(self.cache.values())

    def __getitem__(self, item):
        return self.cache[item]

    async def populate_cache(self):
        for channel in self.bot.guild.text_channels:
            await self.find(channel=channel)

    async def find(self, *, recipient=None, channel=None):
        '''Finds a thread from cache or from discord channel topics.'''
        if recipient is None and channel is not None:
            return await self._find_from_channel(channel)
        try:
            thread = self.cache[recipient.id]
        except KeyError:
            channel = discord.utils.get(
                self.bot.guild.text_channels, 
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
        '''
        Tries to find a thread from a channel channel topic,
        if channel topic doesnt exist for some reason, falls back to 
        searching channel history for genesis embed and extracts user_id fron that.
        '''
        user_id = None

        if channel.topic and 'User ID: ' in channel.topic:
            user_id = int(re.findall(r'\d+', channel.topic)[0])
        elif channel.topic is None and channel.category.name == 'Mod Mail':
            async for message in channel.history():
                if message.embeds:
                    em = message.embeds[0]
                    matches = re.findall(r'<@(\d+)>', str(em.description))
                    if matches:
                        user_id = int(matches[-1])
                        break
        
        if user_id is not None:
            if user_id in self.cache:
                return self.cache[user_id]

            recipient = self.bot.get_user(user_id) # this could be None

            self.cache[user_id] = thread = Thread(self, recipient)
            thread.ready = True
            thread.channel = channel 
            thread.id = user_id

            return thread 

    async def create(self, recipient, *, creator=None):
        '''Creates a modmail thread'''

        em = discord.Embed(
            title='Thread started' if creator else 'Thanks for the message!',
            description='The moderation team will get back to you as soon as possible!',
            color=discord.Color.green()
            )

        if creator is not None:
            em.description = f'{creator.mention} has started a modmail thread with you.'

        asyncio.create_task(recipient.send(embed=em))

        self.cache[recipient.id] = thread = Thread(self, recipient)

        channel = await self.bot.guild.create_text_channel(
            name=self.bot.format_channel_name(recipient),
            category=self.bot.main_category
            )
        
        thread.channel = channel

        log_url, log_data = await asyncio.gather(
            self.bot.modmail_api.get_log_url(recipient, channel, creator or recipient),
            self.bot.modmail_api.get_user_logs(recipient.id)
            )

        log_count = len(log_data)
        info_embed = self.bot.format_info(recipient, creator, log_url, log_count)

        topic = f'User ID: {recipient.id}'
        mention = self.bot.config.get('MENTION', '@here') if not creator else None

        await asyncio.gather(
            channel.edit(topic=topic), 
            channel.send(mention, embed=info_embed)
            )
            
        thread.ready = True
        return thread 
    
    async def find_or_create(self, recipient):
        return await self.find(recipient=recipient) or await self.create(recipient)
