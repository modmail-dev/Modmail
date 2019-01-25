

import datetime
from typing import Optional, Union
import asyncio

import discord
from discord.ext import commands

import dateutil.parser

from core.decorators import trigger_typing
from core.paginator import PaginatorSession
from core.time import UserFriendlyTime, human_timedelta


class Modmail:
    """Commands directly related to Modmail functionality."""

    def __init__(self, bot):
        self.bot = bot

    def obj(arg):
        return discord.Object(int(arg))

    @commands.command()
    @trigger_typing
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        """Sets up a server for Modmail"""
        if self.bot.main_category:
            return await ctx.send(f'{self.bot.modmail_guild} is already set up.')

        categ = await self.bot.modmail_guild.create_category(
            name='Modmail',
            overwrites=self.bot.overwrites(ctx)
        )

        await categ.edit(position=0)

        log_channel = await self.bot.modmail_guild.create_text_channel(name='bot-logs', category=categ)
        await log_channel.edit(topic='You can delete this channel if you set up your own log channel.')
        await log_channel.send('Use the `config set log_channel_id` command to set up a custom log channel.')

        self.bot.config['main_category_id'] = categ.id 
        self.bot.config['log_channel_id'] = log_channel.id
        
        await self.bot.config.update()

        await ctx.send('Successfully set up server.')

    @commands.group(name='snippets')
    @commands.has_permissions(manage_messages=True)
    async def snippets(self, ctx):
        """Returns a list of snippets that are currently set."""
        if ctx.invoked_subcommand is not None:
            return

        embeds = []

        em = discord.Embed(color=discord.Color.blurple())
        em.set_author(name='Snippets', icon_url=ctx.guild.icon_url)

        embeds.append(em)

        em.description = 'Here is a list of snippets that are currently configured.'

        if not self.bot.snippets:
            em.color = discord.Color.red()
            em.description = f'You dont have any snippets at the moment.'
            em.set_footer(text=f'Do {self.bot.prefix}help snippets for more commands.')

        for name, value in self.bot.snippets.items():
            if len(em.fields) == 5:
                em = discord.Embed(color=discord.Color.blurple(), description=em.description)
                em.set_author(name='Snippets', icon_url=ctx.guild.icon_url)
                embeds.append(em)
            em.add_field(name=name, value=value, inline=False)

        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @snippets.command(name='add')
    async def _add(self, ctx, name: str.lower, *, value):
        """Add a snippet to the bot config."""
        if 'snippets' not in self.bot.config.cache:
            self.bot.config['snippets'] = {}

        self.bot.config.snippets[name] = value
        await self.bot.config.update()

        em = discord.Embed(
            title='Added snippet',
            color=discord.Color.blurple(),
            description=f'`{name}` points to: {value}'
        )

        await ctx.send(embed=em)

    @snippets.command(name='del')
    async def __del(self, ctx, *, name: str.lower):
        """Removes a snippet from bot config."""

        em = discord.Embed(
            title='Removed snippet',
            color=discord.Color.blurple(),
            description=f'`{name}` no longer exists.'
        )

        if not self.bot.config.snippets.get(name):
            em.title = 'Error'
            em.color = discord.Color.red()
            em.description = f'Snippet `{name}` does not exist.'
        else:
            del self.bot.config['snippets'][name]
            await self.bot.config.update()

        await ctx.send(embed=em)

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def move(self, ctx, *, category: discord.CategoryChannel):
        """Moves a thread to a specified cateogry."""
        thread = await self.bot.threads.find(channel=ctx.channel)
        if not thread:
            return await ctx.send('This is not a modmail thread.')

        await thread.channel.edit(category=category, sync_permissions=True)
        await ctx.message.add_reaction('✅')

    async def send_scheduled_close_message(self, ctx, after, silent=False):
        human_delta = human_timedelta(after.dt)
        
        silent = '*silently* ' if silent else ''

        em = discord.Embed(
            title='Scheduled close',
            description=f'This thread will close {silent}in {human_delta}.',
            color=discord.Color.red()
            )

        if after.arg and not silent:
            em.add_field(name='Message', value=after.arg)
        
        em.set_footer(text='Closing will be cancelled if a thread message is sent.')
        em.timestamp = after.dt
            
        await ctx.send(embed=em)

    @commands.command(name='close', usage='[after] [close message]')
    async def _close(self, ctx, *, after: UserFriendlyTime=None):
        """Close the current thread.
        
        Close after a period of time:
        - `close in 5 hours`
        - `close 2m30s`
        
        Custom close messages:
        - `close 2 hours The issue has been resolved.`
        - `close We will contact you once we find out more.`

        Silently close a thread (no message)
        - `close silently`
        - `close in 10m silently`

        Cancel closing a thread:
        - close cancel
        """

        thread = await self.bot.threads.find(channel=ctx.channel)
        if not thread:
            return
        
        now = datetime.datetime.utcnow()

        close_after = (after.dt - now).total_seconds() if after else 0
        message = after.arg if after else None
        silent = str(message).lower() in {'silent', 'silently'}
        cancel = str(message).lower() == 'cancel'

        if cancel:
            if thread.close_task is not None:
                await thread.cancel_closure()
                await ctx.send(embed=discord.Embed(color=discord.Color.red(), description='Scheduled close has been cancelled.'))
                return
            return await ctx.send(embed=discord.Embed(color=discord.Color.red(), description='This thread has not already been scheduled to close.'))

        if after and after.dt > now:
            await self.send_scheduled_close_message(ctx, after, silent)

        await thread.close(
            closer=ctx.author, 
            after=close_after,
            message=message, 
            silent=silent,
            )
    
    @commands.command(aliases=['alert'])
    async def notify(self, ctx, *, role=None):
        """Notify a given role or yourself to the next thread message received.
        
        Once a thread message is received you will be pinged once only.
        """
        thread = await self.bot.threads.find(channel=ctx.channel)
        if thread is None:
            return

        if not role:
            mention = ctx.author.mention
        elif role.lower() in ('here', 'everyone'):
            mention = '@' + role 
        else:
            converter = commands.RoleConverter()
            role = await converter.convert(ctx, role)
            mention = role.mention
        
        if str(thread.id) not in self.bot.config['notification_squad']:
            self.bot.config['notification_squad'][str(thread.id)] = []
        
        mentions = self.bot.config['notification_squad'][str(thread.id)]
        
        if mention in mentions:
            return await ctx.send(embed=discord.Embed(color=discord.Color.red(), description=f'{mention} is already going to be mentioned.'))

        mentions.append(mention)
        await self.bot.config.update()
        
        em = discord.Embed(color=discord.Color.blurple())
        em.description = f'{mention} will be mentioned on the next message received.'
        await ctx.send(embed=em)

    @commands.command(aliases=['sub'])
    async def subscribe(self, ctx, *, role=None):
        """Notify yourself or a given role for every thread message recieved.
        You will be pinged for every thread message recieved until you unsubscribe.
        """
        thread = await self.bot.threads.find(channel=ctx.channel)
        if thread is None:
            return

        if not role:
            mention = ctx.author.mention
        elif role.lower() in ('here', 'everyone'):
            mention = '@' + role 
        else:
            converter = commands.RoleConverter()
            role = await converter.convert(ctx, role)
            mention = role.mention
        
        if str(thread.id) not in self.bot.config['subscriptions']:
            self.bot.config['subscriptions'][str(thread.id)] = []
        
        mentions = self.bot.config['subscriptions'][str(thread.id)]
        
        if mention in mentions:
            return await ctx.send(embed=discord.Embed(color=discord.Color.red(), description=f'{mention} is already subscribed to this thread.'))

        mentions.append(mention)
        await self.bot.config.update()

        em = discord.Embed(color=discord.Color.blurple())
        em.description = f'{mention} is now subscribed to be notified of all messages received.'
        await ctx.send(embed=em)

    @commands.command(aliases=['unsub'])
    async def unsubscribe(self, ctx, *, role=None):
        """Unsubscribes a given role or yourself from a thread."""
        thread = await self.bot.threads.find(channel=ctx.channel)
        if thread is None:
            return

        if not role:
            mention = ctx.author.mention
        elif role.lower() in ('here', 'everyone'):
            mention = '@' + role 
        else:
            converter = commands.RoleConverter()
            role = await converter.convert(ctx, role)
            mention = role.mention
        
        if str(thread.id) not in self.bot.config['subscriptions']:
            self.bot.config['subscriptions'][str(thread.id)] = []
        
        mentions = self.bot.config['subscriptions'][str(thread.id)]

        if mention not in mentions:
            return await ctx.send(embed=discord.Embed(color=discord.Color.red(), description=f'{mention} is not already subscribed to this thread.'))
        
        mentions.remove(mention)
        await self.bot.config.update()

        em = discord.Embed(color=discord.Color.blurple())
        em.description = f'{mention} is now unsubscribed to this thread.'
        await ctx.send(embed=em)


    @commands.command()
    async def nsfw(self, ctx):
        """Flags a Modmail thread as nsfw."""
        thread = await self.bot.threads.find(channel=ctx.channel)
        if thread is None:
            return
        await ctx.channel.edit(nsfw=True)
        await ctx.message.add_reaction('✅')

    @commands.command(aliases=['threads'])
    @commands.has_permissions(manage_messages=True)
    @trigger_typing
    async def logs(self, ctx, *, member: Union[discord.Member, discord.User, obj]=None):
        """Shows a list of previous Modmail thread logs of a member."""

        if not member:
            thread = await self.bot.threads.find(channel=ctx.channel)
            if not thread:
                raise commands.UserInputError

        user = member or thread.recipient

        icon_url = getattr(user, 'avatar_url', 'https://cdn.discordapp.com/embed/avatars/0.png')
        username = str(user) if hasattr(user, 'name') else str(user.id)

        logs = await self.bot.modmail_api.get_user_logs(user.id)

        if not any(not e['open'] for e in logs):
            return await ctx.send(embed=discord.Embed(color=discord.Color.red(), description='This user does not have any previous logs'))

        em = discord.Embed(color=discord.Color.blurple())
        em.set_author(name=f'{username} - Previous Logs', icon_url=icon_url)

        embeds = [em]

        current_day = dateutil.parser.parse(logs[0]['created_at']).strftime(r'%d %b %Y')

        fmt = ''

        closed_logs = [l for l in logs if not l['open']]

        for index, entry in enumerate(closed_logs):
            if len(embeds[-1].fields) == 3:
                em = discord.Embed(color=discord.Color.blurple())
                em.set_author(name='Previous Logs', icon_url=icon_url)
                embeds.append(em)

            date = dateutil.parser.parse(entry['created_at'])

            new_day = date.strftime(r'%d %b %Y')
            time = date.strftime(r'%H:%M')

            key = entry['key']
            closer = entry['closer']['name']
            log_url = f"https://logs.modmail.tk/{key}" if not self.bot.selfhosted else self.bot.config.log_url.strip('/') + f'/logs/{key}'

            truncate = lambda c: c[:47].strip() + '...' if len(c) > 50 else c

            if entry['messages']:
                short_desc = truncate(entry['messages'][0]['content']) or 'No content'
            else:
                short_desc = 'No content'

            fmt += f"[`[{time}][closed-by:{closer}]`]({log_url}) - {short_desc}\n"

            if current_day != new_day or index == len(closed_logs) - 1:
                embeds[-1].add_field(name=current_day, value=fmt, inline=False)
                current_day = new_day
                fmt = ''

        session = PaginatorSession(ctx, *embeds)
        await session.run()
        
    @commands.command()
    async def reply(self, ctx, *, msg=''):
        """Reply to users using this command.

        Supports attachments and images as well as automatically embedding image_urls.
        """
        ctx.message.content = msg
        thread = await self.bot.threads.find(channel=ctx.channel)
        if thread:
            await ctx.trigger_typing()
            await thread.reply(ctx.message)
    
    @commands.command()
    async def anonreply(self, ctx, *, msg=''):
        ctx.message.content = msg
        thread = await self.bot.threads.find(channel=ctx.channel)
        if thread:
            await ctx.trigger_typing()
            await thread.reply(ctx.message, anonymous=True)
    
    @commands.command()
    async def note(self, ctx, *, msg=''):
        """Take a note about the current thread, useful for noting context."""
        ctx.message.content = msg 
        thread = await self.bot.threads.find(channel=ctx.channel)

        if thread:
            await ctx.trigger_typing()
            await thread.note(ctx.message)

    @commands.command()
    async def edit(self, ctx, message_id: Optional[int]=None, *, new_message):
        """Edit a message that was sent using the reply command.

        If no message_id is provided, that last message sent by a mod will be edited.

        `[message_id]` the id of the message that you want to edit.
        `<new_message>` is the new message that will be edited in.
        """
        thread = await self.bot.threads.find(channel=ctx.channel)

        if thread is None:
            return

        linked_message_id = None

        async for msg in ctx.channel.history():
            if message_id is None and msg.embeds:
                em = msg.embeds[0]
                mod_color = self.bot.mod_color.value if isinstance(self.bot.mod_color, discord.Color) else self.bot.mod_color
                if em.color.value != mod_color or not em.author.url:
                    continue
                linked_message_id = str(em.author.url).split('/')[-1]
                break
            elif message_id and msg.id == message_id:
                url = msg.embeds[0].author.url
                linked_message_id = str(url).split('/')[-1]
                break

        if not linked_message_id:
            raise commands.UserInputError
        
        await asyncio.gather(
            thread.edit_message(linked_message_id, new_message),
            self.bot.modmail_api.edit_message(linked_message_id, new_message)
        ) 
        await ctx.message.add_reaction('✅')
        

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def contact(self, ctx, category: Optional[discord.CategoryChannel]=None, *, user: Union[discord.Member, discord.User]):
        """Create a thread with a specified member."""

        exists = await self.bot.threads.find(recipient=user)
        if exists:
            return await ctx.send(embed=discord.Embed(color=discord.Color.red(), description=f'A thread for this user already exists in {exists.channel.mention}'))
        else:
            thread = await self.bot.threads.create(user, creator=ctx.author, category=category)

        em = discord.Embed(
            title='Created thread',
            description=f'Thread started in {thread.channel.mention} for {user.mention}',
            color=discord.Color.blurple()
        )

        await ctx.send(embed=em)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def blocked(self, ctx):
        """Returns a list of blocked users"""
        em = discord.Embed(title='Blocked Users', color=discord.Color.blurple(), description='')

        users = []
        not_reachable = []

        for id, reason in self.bot.blocked_users.items():
            user = self.bot.get_user(int(id))
            if user:
                users.append((user, reason))
            else:
                not_reachable.append((id, reason))

        em.description = 'Here is a list of blocked users.'

        if users:
            em.add_field(name='Currently Known', value='\n'.join(u.mention + (f' - `{r}`' if r else '') for u, r in users))
        if not_reachable:
            em.add_field(name='Unknown', value='\n'.join(f'`{i}`' + (f' - `{r}`' if r else '') for i, r in not_reachable), inline=False)

        if not users and not not_reachable:
            em.description = 'Currently there are no blocked users'

        await ctx.send(embed=em)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def block(self, ctx, user: Union[discord.Member, discord.User, obj]=None, *, reason=None):
        """Block a user from using Modmail."""

        if user is None:
            thread = await self.bot.threads.find(channel=ctx.channel)
            if thread:
                user = thread.recipient
            else:
                raise commands.UserInputError

        
        mention = user.mention if hasattr(user, 'mention') else f'`{user.id}`'

        em = discord.Embed()
        em.color = discord.Color.blurple()

        if str(user.id) not in self.bot.blocked_users:
            self.bot.config.blocked[str(user.id)] = reason
            await self.bot.config.update()

            em.title = 'Success'
            em.description = f'{mention} is now blocked ' + (f'for `{reason}`' if reason else '')

            await ctx.send(embed=em)
        else:
            em.title = 'Error'
            em.description = f'{mention} is already blocked'
            em.color = discord.Color.red()

            await ctx.send(embed=em)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def unblock(self, ctx, *, user: Union[discord.Member, discord.User, obj]=None):
        """Unblocks a user from using Modmail."""

        if user is None:
            thread = await self.bot.threads.find(channel=ctx.channel)
            if thread:
                user = thread.recipient
            else:
                raise commands.UserInputError

        mention = user.mention if hasattr(user, 'mention') else f'`{user.id}`'

        em = discord.Embed()
        em.color = discord.Color.blurple()

        if str(user.id) in self.bot.blocked_users:
            del self.bot.config.blocked[str(user.id)]
            await self.bot.config.update()

            em.title = 'Success'
            em.description = f'{mention} is no longer blocked'

            await ctx.send(embed=em)
        else:
            em.title = 'Error'
            em.description = f'{mention} is not blocked'
            em.color = discord.Color.red()

            await ctx.send(embed=em)


def setup(bot):
    bot.add_cog(Modmail(bot))
