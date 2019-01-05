import asyncio
import sqlite3
import re
from datetime import datetime

from discord.ext import commands
from core.utility import owner_only


class Thread:
    statuses = {
        1: 'open',
        2: 'closed',
        3: 'suspended'
    }

    @classmethod
    async def from_data(cls, bot, data, cursor):
        # id	status	is_legacy	user_id	user_name	channel_id	created_at	scheduled_close_at	scheduled_close_id	scheduled_close_name	alert_id
        self = cls()
        self.bot = bot
        self.id = data[0]
        self.status = self.statuses[data[1]]

        user_id = data[3]
        self.recipient = bot.get_user(int(user_id))
        if self.recipient is None:
            self.recipient = await bot.get_user_info(int(user_id))

        self.creator = self.recipient
        self.creator_mod = False
        self.closer = None

        self.channel_id = int(data[5])
        self.created_at = datetime.fromisoformat(data[6])
        self.scheduled_close_at = datetime.fromisoformat(data[7])
        self.scheduled_close_id = data[8]
        self.alert_id = data[9]

        self.messages = []

        for i in cursor.execute("SELECT * FROM 'thread_messages' WHERE thread_id == '?'", self.id):
            message = await ThreadMessage.from_data(i, bot, cursor)
            if message.type == 'command' and 'close' in message.body:
                self.closer = message.user
            elif message.type == 'system' and message.body.startswith('Thread was opened by '):
                # user used the newthread command
                mod = message.body[:21]  # gets name#discrim
                for i in bot.users:
                    if str(i) == mod:
                        self.creator = i
                        self.creator_mod = True
                        break

            self.messages.append(message)
        return self

    def serialize(self):
        """Turns it into a document"""
        payload = {
            'open': self.status != 'closed',
            'channel_id': str(self.channel_id),
            'guild_id': str(self.bot.guild_id),
            'recipient': {
                'id': str(self.recipient.id),
                'name': self.recipient.name,
                'discriminator': self.recipient.discriminator,
                'avatar_url': self.recipient.avatar_url,
                'mod': False
            },
            'creator': {
                'id': str(self.creator.id),
                'name': self.creator.name,
                'discriminator': self.creator.discriminator,
                'avatar_url': self.creator.avatar_url,
                'mod': self.creator_mod
            },
            'messages': [m.serialize() for m in self.messages]
        }
        if self.status == 'closed':
            payload['closer'] = {
                'id': str(self.closer.id),
                'name': self.closer.name,
                'discriminator': self.closer.discriminator,
                'avatar_url': self.closer.avatar_url,
                'mod': True
            }
        return payload
# TODO: Handle if the user closed by himself how does a user close by humself? is that a thing in dragory (yes)


class ThreadMessage:
    types = {
        1: 'system',
        2: 'chat',
        3: 'from_user',
        4: 'to_user',
        5: 'legacy',
        6: 'command'
    }

    @classmethod
    async def from_data(cls, bot, data):
        # id	thread_id	message_type	user_id	user_name	body	is_anonymous	dm_message_id	created_at
        self = cls()
        self.bot = bot
        self.id = data[1]
        self.type = self.types[data[2]]

        user_id = data[3]
        self.user = bot.get_user(int(user_id))
        if self.user is None:
            self.user = await bot.get_user_info(int(user_id))

        self.body = data[5]

        regex = re.compile(r'http:\/\/[\d.]+:\d+\/attachments\/\d+\/.*')
        self.attachments = regex.findall(self.body)
        if self.attachments:
            index = self.body.find(self.attachments[0])
            self.content = self.body[:index]
        else:
            self.content = self.body

        self.is_anonymous = data[6]
        self.dm_message_id = data[6]
        self.created_at = datetime.fromisoformat(data[7])
        self.attachments = regex.findall(self.body)
        return self

    def serialize(self):
        if self.type in ('from_user', 'to_user'):
            return {
                'timestamp': self.created_at,
                'message_id': self.dm_message_id,
                'content': self.content,
                'author': {
                    'id': str(self.author.id),
                    'name': self.author.name,
                    'discriminator': self.author.discriminator,
                    'avatar_url': self.author.avatar_url,
                    'mod': self.type == 'to_user'
                },
                'attachments': self.attachments
            }


class Migrate:
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @owner_only()
    async def migratedragory(self, ctx, url=None):
        try:
            url = url or ctx.message.attachments[0].url
        except IndexError:
            await ctx.send('Provide an sqlite file as the attachment.')

        async with self.bot.session.get(url) as resp:
            with open('dragorydb.sqlite', 'w+') as f:
                f.write(await resp.read())

        conn = sqlite3.connect('dragorydb.sqlite')
        c = conn.cursor()

        output = ''
        # Blocked Users

        for row in c.execute("SELECT * FROM 'blocked_users'"):
            # user_id	user_name	blocked_by	blocked_at

            user_id = row[0]
            categ = self.bot.main_category
            top_chan = categ.channels[0]  # bot-info
            topic = str(top_chan.topic)
            topic += '\n' + str(user_id)

            if str(user_id) not in top_chan.topic:
                await top_chan.edit(topic=topic)
                output += f'Blocked {user_id}\n'
            else:
                output += f'{user_id} already blocked\n'

        # Snippets
        for row in c.execute("SELECT * FROM 'snippets'"):
            # trigger	body	created_by	created_at
            name = row[0]
            value = row[1]

            if 'snippets' not in self.bot.config.cache:
                self.bot.config['snippets'] = {}

            self.bot.config.snippets[name] = value
            output += f'Snippet {name} added: {value}'

        tasks = []

        async def convert_thread_log(row):
            thread = await Thread.from_data(self.bot, row, c)
            converted = thread.serialize()
            print(converted)
            await self.bot.modmail_api.post_log(converted, force=True)

        # Threads
        for row in c.execute("SELECT * FROM 'threads'"):
            tasks.append(convert_thread_log(row))
            output += f'Thread data added: {row[0]}'

        await asyncio.gather(*tasks)
        # TODO: Create channels for non-closed threads

        await self.bot.config.update()

        async with self.bot.session.post('https://hastebin.com/documents', data=output) as resp:
            key = (await resp.json())['key']

        await ctx.send(f'Done. Logs: https://hastebin.com/{key}')


def setup(bot):
    bot.add_cog(Migrate(bot))
