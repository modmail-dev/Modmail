
import discord
from discord.ext import commands
import datetime
import dateutil.parser
from core.decorators import trigger_typing
from core.paginator import PaginatorSession

class Modmail:
    '''Commands directly related to Modmail functionality.'''

    def __init__(self, bot):
        self.bot = bot 

    @commands.command()
    @trigger_typing
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        '''Sets up a server for modmail'''
        if self.bot.main_category:
            return await ctx.send('This server is already set up.')

        categ = await ctx.guild.create_category(
            name='Mod Mail', 
            overwrites=self.bot.overwrites(ctx, modrole=modrole)
            )

        await categ.edit(position=0)

        c = await ctx.guild.create_text_channel(name='thread-logs', category=categ)
        await c.edit(topic='Manually add user id\'s to block users.\n\n'
                           'Blocked\n-------\n\n')

        await ctx.send('Successfully set up server.')
    
    @commands.group(name='snippets')
    @commands.has_permissions(manage_messages=True)
    async def snippets(self, ctx):
        '''Returns a list of snippets that are currently set.'''
        if ctx.invoked_subcommand is not None:
            return 

        embeds = []

        em = discord.Embed(color=discord.Color.green())
        em.set_author(name='Snippets', icon_url=ctx.guild.icon_url)

        embeds.append(em)

        em.description = 'Here is a list of snippets that are currently configured.'

        if not self.bot.snippets:
            em.color = discord.Color.red()
            em.description = f'You dont have any snippets at the moment.'
            em.set_footer(text=f'Do {self.bot.prefix}help snippets for more commands.')
        
        for name, value in self.bot.snippets.items():
            if len(em.fields) == 5:
                em = discord.Embed(color=discord.Color.green(), description=em.description)
                em.set_author(name='Snippets', icon_url=ctx.guild.icon_url)
                embeds.append(em)
            em.add_field(name=name, value=value, inline=False)
        
        session = PaginatorSession(ctx, *embeds)
        await session.run()
    
    @snippets.command(name='add')
    async def _add(self, ctx, name: str.lower, *, value):
        '''Add a snippet to the bot config.'''
        if 'snippets' not in self.bot.config.cache:
            self.bot.config['snippets'] = {}

        self.bot.config.snippets[name] = value
        await self.bot.config.update()

        em = discord.Embed(
            title='Added snippet',
            color=discord.Color.green(),
            description=f'`{name}` points to: {value}'
        )

        await ctx.send(embed=em)

    @snippets.command(name='del')
    async def __del(self, ctx, *, name: str.lower):
        '''Removes a snippet from bot config.'''

        if 'snippets' not in self.bot.config.cache:
            self.bot.config['snippets'] = {}

        em = discord.Embed(
            title='Removed snippet',
            color=discord.Color.green(),
            description=f'`{name}` no longer exists.'
        )

        if not self.bot.config.snippets.get(name):
            em.title = 'Error'
            em.color = discord.Color.red()
            em.description = f'Snippet `{name}` does not exist.'
        else:
            self.bot.config['snippets'][name] = None
            await self.bot.config.update()

        await ctx.send(embed=em)

    @commands.command(name='close')
    @commands.has_permissions(manage_channels=True)
    async def _close(self, ctx):
        '''Close the current thread.'''
        
        thread = await self.bot.threads.find(channel=ctx.channel)
        if not thread:
            return await ctx.send('This is not a modmail thread.')

        await thread.close()

        em = discord.Embed(title='Thread Closed')
        em.description = f'{ctx.author.mention} has closed this modmail thread.'
        em.color = discord.Color.red()

        try:
            await thread.recipient.send(embed=em)
        except:
            pass

        # Logging
        categ = self.bot.main_category
        log_channel = categ.channels[1]

        log_data = await self.bot.modmail_api.post_log(ctx.channel.id, {
            'open': False, 'closed_at': str(datetime.datetime.utcnow()), 'closer': {
                'id': str(ctx.author.id),
                'name': ctx.author.name,
                'discriminator': ctx.author.discriminator,
                'avatar_url': ctx.author.avatar_url,
                'mod': True
            }
        })

        log_url = f"https://logs.modmail.tk/{log_data['user_id']}/{log_data['key']}"

        user = thread.recipient.mention if thread.recipient else f'`{thread.id}`'

        desc = f"[`{log_data['key']}`]({log_url}) {ctx.author.mention} closed a thread with {user}"
        em = discord.Embed(description=desc, color=em.color)
        em.set_author(name='Thread closed', url=log_url)
        await log_channel.send(embed=em)

    @commands.command()
    async def nsfw(self, ctx):
        '''Flags a modmail thread as nsfw.'''
        if ctx.channel.category and ctx.channel.category.name == 'Mod Mail':
            await ctx.edit(nsfw=True)
        em = discord.Embed(description=desc, color=discord.Color.green())
        em.set_author(name='Thread closed', url=log_url)
        await ctx.send('Done')
    
    @commands.command()
    @trigger_typing
    async def logs(self, ctx, *, member: discord.Member=None):
        '''Shows a list of previous modmail thread logs of a member.'''

        if not member:
            thread = await self.bot.threads.find(channel=ctx.channel)
            if not thread:
                raise commands.UserInputError

        user = member or thread.recipient

        logs = await self.bot.modmail_api.get_user_logs(user.id)

        if not any(not e['open'] for e in logs):
            return await ctx.send('This user has no previous logs.')

        em = discord.Embed(color=discord.Color.green())
        em.set_author(name='Previous Logs', icon_url=user.avatar_url)

        embeds = [em]

        current_day = dateutil.parser.parse(logs[0]['created_at']).strftime(r'%d %b %Y')

        fmt = ''

        for index, entry in enumerate(logs):
            if len(embeds[-1].fields) == 3:
                em = discord.Embed(color=discord.Color.green())
                em.set_author(name='Previous Logs', icon_url=user.avatar_url)
                embeds.append(em)

            date = dateutil.parser.parse(entry['created_at'])
            new_day = date.strftime(r'%d %b %Y')
            
            key = entry['key']
            user_id = entry['user_id']
            log_url = f"https://logs.modmail.tk/{user_id}/{key}"
            
            if not entry['open']:  # only list closed threads
                fmt += f"[`{key}`]({log_url})\n"

                if current_day != new_day or index == len(logs) - 2:
                    embeds[-1].add_field(name=current_day, value=fmt)
                    current_day = new_day
                    fmt = ''
        
        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @commands.command()
    @trigger_typing
    async def reply(self, ctx, *, msg=''):
        '''Reply to users using this command.
        
        Supports attachments and images as well as automatically embedding image_urls.
        '''
        ctx.message.content = msg
        thread = await self.bot.threads.find(channel=ctx.channel)
        if thread and thread.channel.category.name == 'Mod Mail':
            await thread.reply(ctx.message)
    
    @commands.command()
    async def edit(self, ctx, message_id: int, *, new_message):
        '''Edit a message that was sent using the reply command.
        
        `<message_id>` is the id shown in the footer of thread messages.
        `<new_message>` is the new message that will be edited in.
        '''
        thread = self.bot.threads.find(channel=ctx.channel)
        if thread and thread.category.name == 'Mod Mail':
            await thread.edit_message(message_id, new_message)
            
    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def contact(self, ctx, *, user: discord.Member):
        '''Create a thread with a specified member.'''

        exists = await self.bot.threads.find(recipient=user)
        if exists:
            return await ctx.send('Thread already exists.')
        else:
            thread = await self.bot.threads.create(user, creator=ctx.author)
        
        em = discord.Embed(
            title='Created thread',
            description=f'Thread started in {thread.channel.mention} for {user.mention}',
            color=discord.Color.green()
            )

        await ctx.send(embed=em)
    
    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def blocked(self, ctx):
        '''Returns a list of blocked users'''
        em = discord.Embed(title='Blocked Users', color=discord.Color.green())
        em.description = ''

        users = []
        not_reachable = []

        for id in self.bot.blocked_users:
            user = self.bot.get_user(id)
            if user:
                users.append(user)
            else:
                not_reachable.append(id)
        
        em.description = 'Here is a list of blocked users.'
        
        if users:
            em.add_field(name='Currently Known', value=' '.join(u.mention for u in users))
        if not_reachable:
            em.add_field(name='Unknown', value='\n'.join(f'`{i}`' for i in not_reachable), inline=False)
        
        if not users and not not_reachable:
            em.description = 'Currently there are no blocked users'

        await ctx.send(embed=em)
        
    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def block(self, ctx, id=None):
        '''Block a user from using modmail.'''

        if id is None:
            thread = await self.bot.threads.find(channel=ctx.channel)
            if thread:
                id = thread.recipient.id
            else:
                raise commands.UserInputError

        categ = self.bot.main_category
        top_chan = categ.channels[0] #bot-info
        topic = str(top_chan.topic)
        topic += '\n' + id

        user = self.bot.get_user(int(id))
        mention = user.mention if user else f'`{id}`'

        em = discord.Embed()
        em.color = discord.Color.green()

        if id not in top_chan.topic:  
            await top_chan.edit(topic=topic)

            em.title = 'Success'
            em.description = f'{mention} is now blocked'

            await ctx.send(embed=em)
        else:
            em.title = 'Error'
            em.description = f'{mention} is already blocked'
            em.color = discord.Color.red()

            await ctx.send(embed=em)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(manage_channels=True)
    async def unblock(self, ctx, id=None):
        '''Unblocks a user from using modmail.'''
        if id is None:
            thread = await self.bot.threads.find(channel=ctx.channel)
            if thread: 
                id = thread.recipient.id
            else:
                raise commands.UserInputError

        categ = discord.utils.get(ctx.guild.categories, name='Mod Mail')
        top_chan = categ.channels[0] #bot-info
        topic = str(top_chan.topic)
        topic = topic.replace('\n'+id, '')

        user = self.bot.get_user(int(id))
        mention = user.mention if user else f'`{id}`'

        em = discord.Embed()
        em.color = discord.Color.green()

        if id in top_chan.topic:  
            await top_chan.edit(topic=topic)

            em.title = 'Success'
            em.description = f'{mention} is no longer blocked'

            await ctx.send(embed=em)
        else:
            em.title = 'Error'
            em.description = f'{mention} is not already blocked'
            em.color = discord.Color.red()

            await ctx.send(embed=em)

def setup(bot):
    bot.add_cog(Modmail(bot))