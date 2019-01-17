from discord import Embed, Color, Activity
from discord.ext import commands
from discord.enums import ActivityType

import traceback
import inspect
from io import StringIO

from datetime import datetime
from textwrap import indent
from contextlib import redirect_stdout
from difflib import get_close_matches

from json import JSONDecodeError
from aiohttp import ClientResponseError

from core.paginator import PaginatorSession
from core.decorators import auth_required, owner_only, trigger_typing
from core.changelog import ChangeLog


class Utility:
    """General commands that provide utility"""

    def __init__(self, bot):
        self.bot = bot

    def format_cog_help(self, ctx, cog):
        """Formats the text for a cog help"""
        sigs = []
        prefix = self.bot.prefix

        for cmd in self.bot.commands:
            if cmd.hidden:
                continue
            if cmd.instance is cog:
                sigs.append(len(cmd.qualified_name) + len(prefix))
                if hasattr(cmd, 'all_commands'):
                    for c in cmd.all_commands.values():
                        sigs.append(len('\u200b  └─ ' + c.name) + 1)

        if not sigs:
            return

        maxlen = max(sigs)

        fmt = ['']
        index = 0
        for cmd in self.bot.commands:
            if cmd.instance is cog:
                if cmd.hidden:
                    continue
                if len(f'{fmt[index]}`{prefix+cmd.qualified_name:<{maxlen}}` '
                       f'- {cmd.short_doc:<{maxlen}}\n') > 1024:
                    index += 1
                    fmt.append('')
                fmt[index] += f'`{prefix+cmd.qualified_name:<{maxlen}}` - '
                fmt[index] += f'{cmd.short_doc:<{maxlen}}\n'
                if hasattr(cmd, 'commands'):
                    for i, c in enumerate(cmd.commands):
                        if len(cmd.commands) == i + 1:  # last
                            branch = '\u200b  └─ ' + c.name
                        else:
                            branch = '\u200b  ├─ ' + c.name
                        if len(f'{fmt[index]}`{branch:<{maxlen+1}}` - '
                               f'{c.short_doc:<{maxlen}}\n') > 1024:
                            index += 1
                            fmt.append('')
                        fmt[index] += f'`{branch:<{maxlen+1}}` - '
                        fmt[index] += f'{c.short_doc:<{maxlen}}\n'

        em = Embed(
            description='*' + inspect.getdoc(cog) + '*',
            color=Color.green()
        )
        em.set_author(name=cog.__class__.__name__ + ' - Help',
                      icon_url=ctx.bot.user.avatar_url)

        for n, i in enumerate(fmt):
            if n == 0:
                em.add_field(name='Commands', value=i)
            else:
                em.add_field(name=u'\u200b', value=i)

        em.set_footer(text=f'Type {prefix}command for more info on a command.')
        return em

    def format_command_help(self, ctx, cmd):
        """Formats command help."""
        prefix = self.bot.prefix
        em = Embed(
            color=Color.green(),
            description=cmd.help
        )

        if hasattr(cmd, 'invoke_without_command') and \
           cmd.invoke_without_command:
            em.title = f'`Usage: {prefix}{cmd.signature}`'
        else:
            em.title = f'`{prefix}{cmd.signature}`'

        if not hasattr(cmd, 'commands'):
            return em

        maxlen = max(len(prefix + str(c)) for c in cmd.commands)
        fmt = ''

        for i, c in enumerate(cmd.commands):
            if len(cmd.commands) == i + 1:  # last
                branch = '└─ ' + c.name
            else:
                branch = '├─ ' + c.name
            fmt += f"`{branch:<{maxlen+1}}` - "
            fmt += f"{c.short_doc:<{maxlen}}\n"

        em.add_field(name='Sub-commands', value=fmt)
        em.set_footer(
            text=f'Type {prefix}help {cmd} command for more info on a command.'
        )
        return em

    def format_not_found(self, ctx, command):
        prefix = ctx.prefix
        em = Embed(
            title='Could not find a cog or command by that name.',
            color=Color.red()
        )
        em.set_footer(text=f'Type {prefix}help to get '
                           'a full list of commands.')
        cogs = get_close_matches(command, self.bot.cogs.keys())
        cmds = get_close_matches(command, self.bot.all_commands.keys())
        if cogs or cmds:
            em.description = 'Did you mean...'
        if cogs:
            em.add_field(name='Cogs', value='\n'.join(f'`{x}`'
                                                      for x in cogs))
        if cmds:
            em.add_field(name='Commands', value='\n'.join(f'`{x}`'
                                                          for x in cmds))
        return em

    @commands.command()
    async def help(self, ctx, *, command: str = None):
        """Shows the help message."""

        await ctx.trigger_typing()

        if command is not None:
            cog = self.bot.cogs.get(command)
            cmd = self.bot.get_command(command)
            if cog is not None:
                em = self.format_cog_help(ctx, cog)
            elif cmd is not None:
                em = self.format_command_help(ctx, cmd)
            else:
                em = self.format_not_found(ctx, command)
            if em:
                return await ctx.send(embed=em)

        pages = []

        for _, cog in sorted(self.bot.cogs.items()):
            em = self.format_cog_help(ctx, cog)
            if em:
                pages.append(em)

        p_session = PaginatorSession(ctx, *pages)

        await p_session.run()
    
    @commands.command()
    @trigger_typing
    async def changelog(self, ctx):
        """Show a paginated changelog of the bot."""
        changelog = await ChangeLog.from_repo(self.bot)
        p = PaginatorSession(ctx, *changelog.embeds)
        await p.run()

    @commands.command(aliases=['bot', 'info'])
    @trigger_typing
    async def about(self, ctx):
        """Shows information about the bot."""
        em = Embed(color=0x36393F,
                   timestamp=datetime.utcnow())
        em.set_author(name='Mod Mail - About',
                      icon_url=self.bot.user.avatar_url)
        em.set_thumbnail(url=self.bot.user.avatar_url)

        em.description = ('This is an open source discord bot that serves '
                          'as a means for members to easily communicate with '
                          'server leadership in an organised manner.')

        url = 'https://api.modmail.tk/metadata'
        async with self.bot.session.get(url) as resp:
            try:
                meta = await resp.json()
            except (JSONDecodeError, ClientResponseError):
                meta = None

        em.add_field(name='Uptime', value=self.bot.uptime)
        if meta:
            em.add_field(name='Instances', value=meta['instances'])
        else:
            em.add_field(name='Latency',
                         value=f'{self.bot.latency*1000:.2f} ms')

        em.add_field(name='Version',
                     value=f'[`{self.bot.version}`]'
                           '(https://modmail.tk/changelog)')
        em.add_field(name='Author',
                     value='[`kyb3r`](https://github.com/kyb3r)')

        footer = f'Bot ID: {self.bot.user.id}'

        if meta:
            if self.bot.version != meta['latest_version']:
                footer = ("A newer version is available "
                          f"v{meta['latest_version']}")
            else:
                footer = 'You are up to date with the latest version.'

        em.add_field(name='Github',
                     value='https://github.com/kyb3r/modmail',
                     inline=False)

        em.set_footer(text=footer)
        await ctx.send(embed=em)

    @commands.command()
    @owner_only()
    @auth_required
    @trigger_typing
    async def github(self, ctx):
        """Shows the github user your access token is linked to."""
        if ctx.invoked_subcommand:
            return

        data = await self.bot.modmail_api.get_user_info()

        em = Embed(
            title='Github',
            description='Current User',
            color=Color.green()
        )
        user = data['user']
        em.set_author(name=user['username'],
                      icon_url=user['avatar_url'],
                      url=user['url'])
        em.set_thumbnail(url=user['avatar_url'])
        await ctx.send(embed=em)

    @commands.command()
    @owner_only()
    @auth_required
    @trigger_typing
    async def update(self, ctx):
        """Updates the bot, this only works with heroku users."""
        metadata = await self.bot.modmail_api.get_metadata()

        desc = (f'The latest version is [`{self.bot.version}`]'
                '(https://github.com/kyb3r/modmail/blob/master/bot.py#L25)')

        em = Embed(
            title='Already up to date',
            description=desc,
            color=Color.green()
        )

        if metadata['latest_version'] == self.bot.version:
            data = await self.bot.modmail_api.get_user_info()
            if not data.get('error'):
                user = data['user']
                em.set_author(name=user['username'],
                              icon_url=user['avatar_url'],
                              url=user['url'])
        else:
            data = await self.bot.modmail_api.update_repository()

            commit_data = data['data']
            user = data['user']
            em.title = None
            em.set_author(name=user['username'],
                          icon_url=user['avatar_url'],
                          url=user['url'])
            em.set_footer(text=f'Updating modmail v{self.bot.version} '
                               f"-> v{metadata['latest_version']}")

            if commit_data:
                em.set_author(name=user['username'] + ' - Updating bot',
                              icon_url=user['avatar_url'],
                              url=user['url'])
                changelog = await ChangeLog.from_repo(self.bot)
                latest = changelog.latest_version
                em.description = latest.description
                for name, value in latest.fields.items():
                    em.add_field(name=name, value=value)
                # TODO: message unused?
                message = commit_data['commit']['message']
                html_url = commit_data["html_url"]
                short_sha = commit_data['sha'][:6]
                em.add_field(name='Merge Commit',
                             value=f'[`{short_sha}`]({html_url})')
            else:
                em.description = 'Already up to date with master repository.'

        return await ctx.send(embed=em)

    @commands.command(aliases=['presence'])
    @commands.has_permissions(administrator=True)
    async def activity(self, ctx, activity_type: str, *, message: str = ''):
        """
        Set a custom activity for the bot.

        Possible activity types:
            - `playing`
            - `streaming`
            - `listening`
            - `watching`
            - `clear`

        When activity type is set to `clear`, the current activity is removed.
        """
        if activity_type == 'clear':
            await self.bot.change_presence(activity=None)
            self.bot.config['activity_type'] = None
            self.bot.config['activity_message'] = None
            await self.bot.config.update()
            em = Embed(
                title='Activity Removed',
                color=Color.green()
            )
            return await ctx.send(embed=em)

        if not message:
            raise commands.UserInputError

        try:
            activity_type = ActivityType[activity_type]
        except KeyError:
            raise commands.UserInputError

        if activity_type == ActivityType.streaming:
            url = self.bot.config.get('twitch_url',
                                      'https://www.twitch.tv/discord-modmail/')
        else:
            url = None
        activity = Activity(type=activity_type, name=message, url=url)
        await self.bot.change_presence(activity=activity)

        self.bot.config['activity_type'] = activity_type
        self.bot.config['activity_message'] = message
        await self.bot.config.update()

        desc = f'Current activity is: {activity_type.name} {message}.'
        em = Embed(
            title='Activity Changed',
            description=desc,
            color=Color.green()
        )
        return await ctx.send(embed=em)

    @commands.command()
    @trigger_typing
    @commands.has_permissions(administrator=True)
    async def ping(self, ctx):
        """Pong! Returns your websocket latency."""
        em = Embed(
            title='Pong! Websocket Latency:',
            description=f'{self.bot.ws.latency * 1000:.4f} ms',
            color=0x00FF00
        )
        return await ctx.send(embed=em)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def mention(self, ctx, *, mention=None):
        """Changes what the bot mentions at the start of each thread."""
        current = self.bot.config.get('mention', '@here')

        if mention is None:
            em = Embed(
                title='Current text',
                color=Color.green(),
                description=f'{current}'
            )

        else:
            em = Embed(
                title='Changed mention!',
                description=f'On thread creation the bot now says {mention}',
                color=Color.green()
            )
            self.bot.config['mention'] = mention
            await self.bot.config.update()

        return await ctx.send(embed=em)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def prefix(self, ctx, *, prefix=None):
        """Changes the prefix for the bot."""

        current = self.bot.prefix
        em = Embed(
            title='Current prefix',
            color=Color.green(),
            description=f'{current}'
        )

        if prefix is None:
            await ctx.send(embed=em)
        else:
            em.title = 'Changed prefix!'
            em.description = f'Set prefix to `{prefix}`'
            self.bot.config['prefix'] = prefix
            await self.bot.config.update()
            await ctx.send(embed=em)

    @commands.group()
    @owner_only()
    async def config(self, ctx):
        """
        Change configuration for the bot.

        You shouldn't have to use these commands as other commands such
        as `prefix` and `activity` should change config vars for you.
        """
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command('help')
            await ctx.invoke(cmd, command='config')

    @config.command()
    async def set(self, ctx, key: str.lower, *, value):
        """
        Sets a configuration variable and its value
        """

        keys = self.bot.config.allowed_to_change_in_command

        if key in keys:
            em = Embed(
                title='Success',
                color=Color.green(),
                description=f'Set `{key}` to `{value}`'
            )
            await self.bot.config.update({key: value})
        else:
            em = Embed(
                title='Error',
                color=Color.red(),
                description=f'{key} is an invalid key.'
            )
            valid_keys = [f'`{k}`' for k in keys]
            em.add_field(name='Valid keys', value=', '.join(valid_keys))

        return await ctx.send(embed=em)

    @config.command(name='del')
    async def del_(self, ctx, key: str.lower):
        """Sets a specified key from the config to nothing."""
        keys = self.bot.config.allowed_to_change_in_command
        if key in keys:
            em = Embed(
                title='Success',
                color=Color.green(),
                description=f'Set `{key}` to nothing.'
            )
            del self.bot.config.cache[key]
            await self.bot.config.update()
        else:
            em = Embed(
                title='Error',
                color=Color.red(),
                description=f'{key} is an invalid key.'
            )
            valid_keys = [f'`{k}`' for k in keys]
            em.add_field(name='Valid keys', value=', '.join(valid_keys))

        return await ctx.send(embed=em)

    @config.command()
    async def get(self, ctx, key=None):
        """Shows the config variables that are currently set."""
        keys = self.bot.config.allowed_to_change_in_command

        if key:
            if key in keys:
                desc = f'`{key}` is set to `{self.bot.config.get(key)}`'
                em = Embed(
                    color=Color.green(),
                    description=desc
                )
                em.set_author(name='Config variable',
                              icon_url=self.bot.user.avatar_url)

            else:
                em = Embed(
                    title='Error',
                    color=Color.red(),
                    description=f'`{key}` is an invalid key.'
                )
                valid_keys = [f'`{k}`' for k in keys]
                em.add_field(name='Valid keys', value=', '.join(valid_keys))

        else:
            em = Embed(
                color=Color.green(),
                description='Here is a list of currently '
                            'set configuration variables.'
            )
            em.set_author(name='Current config',
                          icon_url=self.bot.user.avatar_url)

            config = {
                k: v for k, v in self.bot.config.cache.items()
                if v and k in keys
            }

            for k, v in reversed(list(config.items())):
                em.add_field(name=k, value=f'`{v}`', inline=False)

        return await ctx.send(embed=em)

    @commands.group(aliases=['aliases'])
    @commands.has_permissions(manage_messages=True)
    async def alias(self, ctx):
        """Returns a list of aliases that are currently set."""
        if ctx.invoked_subcommand is not None:
            return

        embeds = []
        desc = 'Here is a list of aliases that are currently configured.'

        if self.bot.aliases:
            em = Embed(
                color=Color.green(),
                description=desc
            )
        else:
            em = Embed(
                color=Color.red(),
                description='You dont have any aliases at the moment.'
            )
        em.set_author(name='Command aliases', icon_url=ctx.guild.icon_url)
        em.set_footer(text=f'Do {self.bot.prefix}'
                           'help aliases for more commands.')
        embeds.append(em)

        for name, value in self.bot.aliases.items():
            if len(em.fields) == 5:
                em = Embed(color=Color.green(), description=desc)
                em.set_author(name='Command aliases',
                              icon_url=ctx.guild.icon_url)
                em.set_footer(text=f'Do {self.bot.prefix}help '
                                   'aliases for more commands.')
                embeds.append(em)
            em.add_field(name=name, value=value, inline=False)

        session = PaginatorSession(ctx, *embeds)
        return await session.run()

    @alias.command(name='add')
    async def add_(self, ctx, name: str.lower, *, value):
        """Add an alias to the bot config."""
        if 'aliases' not in self.bot.config.cache:
            self.bot.config['aliases'] = {}
        
        # TODO: Make embed
        if self.bot.get_command(name) or self.bot.config.aliases.get(name):
            return await ctx.send('A command or alias already exists '
                                  f'with the same name: `{name}`')
        
        if not self.bot.get_command(value.split()[0]):
            return await ctx.send('The command you are attempting to point '
                                  f'to does not exist: `{value.split()[0]}`')

        self.bot.config.aliases[name] = value
        await self.bot.config.update()

        em = Embed(
            title='Added alias',
            color=Color.green(),
            description=f'`{name}` points to: {value}'
        )

        return await ctx.send(embed=em)

    @alias.command(name='del')
    # TODO: Potential Bug. Does functions override in discord??
    async def del_(self, ctx, *, name: str.lower):
        """Removes a alias from bot config."""

        if 'aliases' not in self.bot.config.cache:
            self.bot.config['aliases'] = {}

        if self.bot.config.aliases.get(name):
            del self.bot.config['aliases'][name]
            await self.bot.config.update()
            
            em = Embed(
                title='Removed alias',
                color=Color.green(),
                description=f'`{name}` no longer exists.'
            )
            
        else:
            em = Embed(
                title='Error',
                color=Color.red(),
                description=f'Alias `{name}` does not exist.'
            )

        return await ctx.send(embed=em)

    @commands.command(hidden=True, name='eval')
    @owner_only()
    async def eval_(self, ctx, *, body):
        """Evaluates python code"""
        
        # TODO: Ugly func, fix.
        env = {
            'ctx': ctx,
            'bot': self.bot,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            'source': inspect.getsource,
        }

        env.update(globals())

        def cleanup_code(content):
            """Automatically removes code blocks from the code."""
            # remove ```py\n```
            if content.startswith('```') and content.endswith('```'):
                return '\n'.join(content.split('\n')[1:-1])

            # remove `foo`
            return content.strip('` \n')

        body = cleanup_code(body)
        stdout = StringIO()

        to_compile = f'async def func():\n{indent(body, "  ")}'

        def paginate(text: str):
            """Simple generator that paginates text."""
            last = 0
            pages = []
            appd_index = curr = None
            for curr in range(0, len(text)):
                if curr % 1980 == 0:
                    pages.append(text[last:curr])
                    last = curr
                    appd_index = curr
            if appd_index != len(text) - 1:
                pages.append(text[last:curr])
            return list(filter(lambda a: a != '', pages))

        try:
            exec(to_compile, env)
        except Exception as e:
            await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')
            return await ctx.message.add_reaction('\u2049')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
            return await ctx.message.add_reaction('\u2049')

        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        await ctx.send(f'```py\n{value}\n```')
                    except Exception:
                        paginated_text = paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                await ctx.send(f'```py\n{page}\n```')
                                break
                            await ctx.send(f'```py\n{page}\n```')
            else:
                try:
                    await ctx.send(f'```py\n{value}{ret}\n```')
                except Exception:
                    paginated_text = paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            await ctx.send(f'```py\n{page}\n```')
                            break
                        await ctx.send(f'```py\n{page}\n```')


def setup(bot):
    bot.add_cog(Utility(bot))
