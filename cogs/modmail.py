import discord
from discord.ext import commands

from datetime import datetime
from typing import Optional, Union

from dateutil import parser

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
            return await ctx.send(
                f'{self.bot.modmail_guild} is already set up.')

        category = await self.bot.modmail_guild.create_category(
            name='Modmail',
            overwrites=self.bot.overwrites(ctx)
        )

        await category.edit(position=0)

        log_channel = await self.bot.modmail_guild.create_text_channel(
            name='bot-logs', category=category
        )

        await log_channel.edit(
            topic='You can delete this channel '
                  'if you set up your own log channel.'
        )

        await log_channel.send(
            'Use the `config set log_channel_id` '
            'command to set up a custom log channel.'
        )

        self.bot.config['main_category_id'] = category.id
        self.bot.config['log_channel_id'] = log_channel.id

        await self.bot.config.update()
        await ctx.send('Successfully set up server.')

    @commands.group()
    @commands.has_permissions(manage_messages=True)
    async def snippets(self, ctx):
        """Returns a list of snippets that are currently set."""
        if ctx.invoked_subcommand is not None:
            return

        embeds = []

        if self.bot.snippets:
            embed = discord.Embed(color=discord.Color.blurple(),
                                  description='Here is a list of snippets '
                                              'that are currently configured.')
        else:
            embed = discord.Embed(
                color=discord.Color.red(),
                description='You dont have any snippets at the moment.'
            )
            embed.set_footer(
                text=f'Do {self.bot.prefix}help snippets for more commands.'
            )

        embed.set_author(name='Snippets', icon_url=ctx.guild.icon_url)
        embeds.append(embed)

        for name, value in self.bot.snippets.items():
            if len(embed.fields) == 5:
                embed = discord.Embed(color=discord.Color.blurple(),
                                      description=embed.description)
                embed.set_author(name='Snippets', icon_url=ctx.guild.icon_url)
                embeds.append(embed)
            embed.add_field(name=name, value=value, inline=False)

        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @snippets.command(name='add')
    async def add_(self, ctx, name: str.lower, *, value):
        """Add a snippet to the bot config."""
        if 'snippets' not in self.bot.config.cache:
            self.bot.config['snippets'] = {}

        self.bot.config.snippets[name] = value
        await self.bot.config.update()

        embed = discord.Embed(
            title='Added snippet',
            color=discord.Color.blurple(),
            description=f'`{name}` points to: {value}'
        )

        await ctx.send(embed=embed)

    @snippets.command(name='del')
    async def del_(self, ctx, *, name: str.lower):
        """Removes a snippet from bot config."""

        if self.bot.config.snippets.get(name):
            embed = discord.Embed(
                title='Removed snippet',
                color=discord.Color.blurple(),
                description=f'`{name}` no longer exists.'
            )
            del self.bot.config['snippets'][name]
            await self.bot.config.update()

        else:
            embed = discord.Embed(
                title='Error',
                color=discord.Color.red(),
                description=f'Snippet `{name}` does not exist.'
            )

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def move(self, ctx, *, category: discord.CategoryChannel):
        """Moves a thread to a specified category."""
        thread = await self.bot.threads.find(channel=ctx.channel)
        if not thread:
            return await ctx.send('This is not a modmail thread.')

        await thread.channel.edit(category=category, sync_permissions=True)
        await ctx.message.add_reaction('✅')

    async def send_scheduled_close_message(self, ctx, after, silent=False):
        human_delta = human_timedelta(after.dt)
        
        silent = '*silently* ' if silent else ''

        embed = discord.Embed(
            title='Scheduled close',
            description=f'This thread will close {silent}in {human_delta}.',
            color=discord.Color.red()
        )

        if after.arg and not silent:
            embed.add_field(name='Message', value=after.arg)
        
        embed.set_footer(text='Closing will be cancelled '
                              'if a thread message is sent.')
        embed.timestamp = after.dt

        await ctx.send(embed=embed)

    @commands.command(usage='[after] [close message]')
    async def close(self, ctx, *, after: UserFriendlyTime = None):
        """
        Close the current thread.
        
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
        
        now = datetime.utcnow()

        close_after = (after.dt - now).total_seconds() if after else 0
        message = after.arg if after else None
        silent = str(message).lower() in {'silent', 'silently'}
        cancel = str(message).lower() == 'cancel'

        if cancel:

            if thread.close_task is not None:
                await thread.cancel_closure()
                embed = discord.Embed(color=discord.Color.red(),
                                      description='Scheduled close '
                                                  'has been cancelled.')
            else:
                embed = discord.Embed(
                    color=discord.Color.red(),
                    description='This thread has not already '
                                'been scheduled to close.'
                )

            return await ctx.send(embed=embed)

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
        """
        Notify a given role or yourself to the next thread message received.
        
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
            embed = discord.Embed(color=discord.Color.red(),
                                  description=f'{mention} is already '
                                              'going to be mentioned.')
        else:
            mentions.append(mention)
            await self.bot.config.update()
            embed = discord.Embed(color=discord.Color.blurple(),
                                  description=f'{mention} will be mentioned '
                                              'on the next message received.')
        return await ctx.send(embed=embed)

    @commands.command(aliases=['sub'])
    async def subscribe(self, ctx, *, role=None):
        """
        Notify yourself or a given role for every thread message received.

        You will be pinged for every thread message
        received until you unsubscribe.
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
            embed = discord.Embed(color=discord.Color.red(),
                                  description=f'{mention} is already '
                                              'subscribed to this thread.')
        else:
            mentions.append(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=discord.Color.blurple(),
                description=f'{mention} will now be '            
                            'notified of all messages received.'
            )
        return await ctx.send(embed=embed)

    @commands.command(aliases=['unsub'])
    async def unsubscribe(self, ctx, *, role=None):
        """Unsubscribe yourself or a given role from a thread."""
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
            embed = discord.Embed(color=discord.Color.red(),
                                  description=f'{mention} is not already '
                                              'subscribed to this thread.')
        else:
            mentions.remove(mention)
            await self.bot.config.update()
            embed = discord.Embed(color=discord.Color.blurple(),
                                  description=f'{mention} is now unsubscribed '
                                              'to this thread.')
        return await ctx.send(embed=embed)

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
    async def logs(self, ctx, *,
                   member: Union[discord.Member, discord.User, obj] = None):
        """Shows a list of previous Modmail thread logs of a member."""
        # TODO: find a better way of that Union ^
        if not member:
            thread = await self.bot.threads.find(channel=ctx.channel)
            if not thread:
                raise commands.UserInputError
            user = thread.recipient
        else:
            user = member

        default_avatar = 'https://cdn.discordapp.com/embed/avatars/0.png'
        icon_url = getattr(user, 'avatar_url', default_avatar)
        username = str(user) if hasattr(user, 'name') else str(user.id)

        logs = await self.bot.modmail_api.get_user_logs(user.id)

        if not any(not log['open'] for log in logs):
            embed = discord.Embed(color=discord.Color.red(),
                                  description='This user does not '
                                              'have any previous logs.')
            return await ctx.send(embed=embed)

        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_author(name=f'{username} - Previous Logs', icon_url=icon_url)

        embeds = [embed]

        current_day = parser.parse(logs[0]['created_at'])
        current_day = current_day.strftime(r'%d %b %Y')

        fmt = ''

        closed_logs = [l for l in logs if not l['open']]

        for index, entry in enumerate(closed_logs):
            if len(embeds[-1].fields) == 3:
                embed = discord.Embed(color=discord.Color.blurple())
                embed.set_author(name='Previous Logs', icon_url=icon_url)
                embeds.append(embed)

            date = parser.parse(entry['created_at'])

            new_day = date.strftime(r'%d %b %Y')
            time = date.strftime(r'%H:%M')

            key = entry['key']
            closer = entry['closer']['name']

            if not self.bot.self_hosted:
                log_url = f"https://logs.modmail.tk/{key}"
            else:
                log_url = self.bot.config.log_url.strip('/') + f'/logs/{key}'

            # TODO: Move all the lambda-like functions to a utils.py
            def truncate(c):
                return c[:47].strip() + '...' if len(c) > 50 else c

            if entry['messages']:
                short_desc = truncate(entry['messages'][0]['content'])
                if not short_desc:
                    short_desc = 'No content'
            else:
                short_desc = 'No content'

            fmt += (f'[`[{time}][closed-by:{closer}]`]'
                    f'({log_url}) - {short_desc}\n')

            if current_day != new_day or index == len(closed_logs) - 1:
                embeds[-1].add_field(name=current_day, value=fmt, inline=False)
                current_day = new_day
                fmt = ''

        session = PaginatorSession(ctx, *embeds)
        await session.run()
        
    @commands.command()
    @trigger_typing
    async def reply(self, ctx, *, msg=''):
        """Reply to users using this command.

        Supports attachments and images as well as
        automatically embedding image URLs.
        """
        ctx.message.content = msg
        thread = await self.bot.threads.find(channel=ctx.channel)
        if thread:
            await thread.reply(ctx.message)
    
    @commands.command()
    @trigger_typing
    async def note(self, ctx, *, msg=''):
        """Take a note about the current thread, useful for noting context."""
        ctx.message.content = msg 
        thread = await self.bot.threads.find(channel=ctx.channel)
        if thread:
            await thread.note(ctx.message)

    @commands.command()
    async def edit(self, ctx, message_id: Optional[int] = None,
                   *, new_message):
        """Edit a message that was sent using the reply command.

        If no `message_id` is provided, that
        last message sent by a mod will be edited.

        `[message_id]` the id of the message that you want to edit.
        `new_message` is the new message that will be edited in.
        """
        thread = await self.bot.threads.find(channel=ctx.channel)

        if thread is None:
            return

        linked_message_id = None

        async for msg in ctx.channel.history():
            if message_id is None and msg.embeds:
                embed = msg.embeds[0]
                if isinstance(self.bot.mod_color, discord.Color):
                    mod_color = self.bot.mod_color.value
                else:
                    mod_color = self.bot.mod_color
                if embed.color.value != mod_color or not embed.author.url:
                    continue
                linked_message_id = str(embed.author.url).split('/')[-1]
                break
            elif message_id and msg.id == message_id:
                url = msg.embeds[0].author.url
                linked_message_id = str(url).split('/')[-1]
                break

        if not linked_message_id:
            raise commands.UserInputError

        await thread.edit_message(linked_message_id, new_message)
        await ctx.message.add_reaction('✅')

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def contact(self, ctx,
                      category: Optional[discord.CategoryChannel] = None, *,
                      user: Union[discord.Member, discord.User]):
        """Create a thread with a specified member."""

        exists = await self.bot.threads.find(recipient=user)
        if exists:
            embed = discord.Embed(
                color=discord.Color.red(),
                description='A thread for this user already '
                            f'exists in {exists.channel.mention}.'
            )

        else:
            thread = await self.bot.threads.create(user, creator=ctx.author,
                                                   category=category)
            embed = discord.Embed(
                title='Created thread',
                description=f'Thread started in {thread.channel.mention} '
                            f'for {user.mention}',
                color=discord.Color.blurple()
            )

        return await ctx.send(embed=embed)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def blocked(self, ctx):
        """Returns a list of blocked users"""
        embed = discord.Embed(title='Blocked Users',
                              color=discord.Color.blurple(),
                              description='Here is a list of blocked users.')

        users = []
        not_reachable = []

        for id_, reason in self.bot.blocked_users.items():
            user = self.bot.get_user(int(id_))
            if user:
                users.append((user, reason))
            else:
                not_reachable.append((id_, reason))

        if users:
            val = '\n'.join(u.mention + (f' - `{r}`' if r else '')
                            for u, r in users)
            embed.add_field(name='Currently Known', value=val)
        if not_reachable:
            val = '\n'.join(f'`{i}`' + (f' - `{r}`' if r else '')
                            for i, r in not_reachable)
            embed.add_field(name='Unknown', value=val, inline=False)

        if not users and not not_reachable:
            embed.description = 'Currently there are no blocked users'

        await ctx.send(embed=embed)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def block(self, ctx,
                    user: Union[discord.Member, discord.User, obj] = None,
                    *, reason=None):
        """Block a user from using Modmail."""

        if user is None:
            thread = await self.bot.threads.find(channel=ctx.channel)
            if thread:
                user = thread.recipient
            else:
                raise commands.UserInputError
        
        mention = user.mention if hasattr(user, 'mention') else f'`{user.id}`'

        if str(user.id) not in self.bot.blocked_users:
            self.bot.config.blocked[str(user.id)] = reason
            await self.bot.config.update()
            extend = f'for `{reason}`' if reason else ''
            embed = discord.Embed(
                title='Success',
                color=discord.Color.blurple(),
                description=f'{mention} is now blocked ' + extend
            )
        else:
            embed = discord.Embed(
                title='Error',
                color=discord.Color.red(),
                description=f'{mention} is already blocked'
            )

        return await ctx.send(embed=embed)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def unblock(self, ctx, *,
                      user: Union[discord.Member, discord.User, obj] = None):
        """Unblocks a user from using Modmail."""

        if user is None:
            thread = await self.bot.threads.find(channel=ctx.channel)
            if thread:
                user = thread.recipient
            else:
                raise commands.UserInputError

        mention = user.mention if hasattr(user, 'mention') else f'`{user.id}`'

        if str(user.id) in self.bot.blocked_users:
            del self.bot.config.blocked[str(user.id)]
            await self.bot.config.update()
            embed = discord.Embed(
                title='Success',
                color=discord.Color.blurple(),
                description=f'{mention} is no longer blocked'
            )
        else:
            embed = discord.Embed(
                title='Error',
                description=f'{mention} is not blocked',
                color=discord.Color.red()
            )

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Modmail(bot))
