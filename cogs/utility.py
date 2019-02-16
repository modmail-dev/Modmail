import inspect
import logging
import os
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from difflib import get_close_matches
from io import StringIO
from json import JSONDecodeError
from textwrap import indent

import discord
from discord import Embed, Color, Activity
from discord.enums import ActivityType, Status
from discord.ext import commands

from aiohttp import ClientResponseError

from core import checks
from core.changelog import Changelog
from core.decorators import github_access_token_required, trigger_typing
from core.models import Bot, InvalidConfigError
from core.paginator import PaginatorSession, MessagePaginatorSession
from core.utils import cleanup_code, info, error

logger = logging.getLogger('Modmail')


class Utility:
    """General commands that provide utility"""

    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    async def verify_checks(ctx, cmd):
        predicates = cmd.checks
        if not predicates:
            return True

        try:
            return await discord.utils.async_all(predicate(ctx)
                                                 for predicate in predicates)
        except commands.CheckFailure:
            return False

    async def format_cog_help(self, ctx, cog):
        """Formats the text for a cog help"""

        prefix = self.bot.prefix

        fmts = ['']
        for cmd in sorted(self.bot.commands,
                          key=lambda cmd: cmd.qualified_name):
            if cmd.instance is cog and not cmd.hidden and \
                    await self.verify_checks(ctx, cmd):
                new_fmt = f'`{prefix + cmd.qualified_name}` - '
                new_fmt += f'{cmd.short_doc}\n'
                if len(new_fmt) + len(fmts[-1]) >= 1024:
                    fmts.append(new_fmt)
                else:
                    fmts[-1] += new_fmt

        embeds = []
        for fmt in fmts:
            if fmt == '':
                continue
            embed = Embed(
                description='*' + (inspect.getdoc(cog) or
                                   'No description') + '*',
                color=self.bot.main_color
            )

            embed.add_field(name='Commands', value=fmt)
            embed.set_author(name=cog.__class__.__name__ + ' - Help',
                             icon_url=ctx.bot.user.avatar_url)

            embed.set_footer(text=f'Type "{prefix}help command" '
                                  'for more info on a command.')
            embeds.append(embed)
        return embeds

    async def format_command_help(self, ctx, cmd):
        """Formats command help."""
        if cmd.hidden or not await self.verify_checks(ctx, cmd):
            return None

        prefix = self.bot.prefix
        embed = Embed(
            color=self.bot.main_color,
            description=cmd.help
        )

        embed.title = f'`{prefix}{cmd.signature}`'

        if not isinstance(cmd, commands.Group):
            return embed

        fmt = ''
        length = len(cmd.all_commands)
        for i, (name, c) in enumerate(sorted(cmd.all_commands.items(),
                                             key=lambda c: c[0])):
            if length == i + 1:  # last
                branch = '└─'
            else:
                branch = '├─'
            fmt += f"`{branch} {name}` - {c.short_doc}\n"

        embed.add_field(name='Sub Commands', value=fmt)
        embed.set_footer(
            text=f'Type "{prefix}help {cmd} command" '
            'for more info on a command.'
        )
        return embed

    async def format_not_found(self, ctx, command):
        prefix = ctx.prefix
        embed = Embed(
            title='Unable to Find Command or Category',
            color=Color.red()
        )
        embed.set_footer(text=f'Type "{prefix}help" to get '
                              'a full list of commands.')

        choices = set()
        # filter out hidden commands & blank cogs
        for i in self.bot.cogs:
            for cmd in self.bot.commands:
                if cmd.cog_name == i and not cmd.hidden and \
                        await self.verify_checks(ctx, cmd):
                    # as long as there's one valid cmd, add cog
                    choices.add(i)
                    break

        for i in self.bot.commands:
            if not i.hidden and await self.verify_checks(ctx, i):
                choices.add(i.name)

        closest = get_close_matches(command, choices, n=1, cutoff=0.45)
        if closest:
            # Perhaps you meant:
            #  - `item`
            embed.description = (f'**Perhaps you meant:**\n'
                                 f'\u2000- `{closest[0]}`')
        return embed

    @commands.command(name='help')
    @trigger_typing
    async def help_(self, ctx, *, command: str = None):
        """Shows the help message."""

        if command:
            cmd = self.bot.get_command(command)
            cog = self.bot.cogs.get(command)
            embeds = []

            if cmd:
                help_msg = await self.format_command_help(ctx, cmd)
                if help_msg:
                    embeds = [help_msg]

            elif cog:
                # checks if cog has commands
                embeds = await self.format_cog_help(ctx, cog)

            if not embeds:
                embeds = [await self.format_not_found(ctx, command)]

            p_session = PaginatorSession(ctx, *embeds)
            return await p_session.run()

        embeds = []
        for cog in sorted(self.bot.cogs.values(),
                          key=lambda cog: cog.__class__.__name__):
            embeds.extend(await self.format_cog_help(ctx, cog))

        p_session = PaginatorSession(ctx, *embeds)
        return await p_session.run()

    @commands.command()
    @trigger_typing
    async def changelog(self, ctx):
        """Show a paginated changelog of the bot."""
        changelog = await Changelog.from_url(self.bot)
        paginator = PaginatorSession(ctx, *changelog.embeds)
        await paginator.run()

    @commands.command(aliases=['bot', 'info'])
    @trigger_typing
    async def about(self, ctx):
        """Shows information about the bot."""
        embed = Embed(color=self.bot.main_color,
                      timestamp=datetime.utcnow())
        embed.set_author(name='Modmail - About',
                         icon_url=self.bot.user.avatar_url)
        embed.set_thumbnail(url=self.bot.user.avatar_url)

        desc = 'This is an open source Discord bot that serves as a means for '
        desc += 'members to easily communicate with server administrators in '
        desc += 'an organised manner.'
        embed.description = desc

        url = 'https://api.modmail.tk/metadata'
        async with self.bot.session.get(url) as resp:
            try:
                meta = await resp.json()
            except (JSONDecodeError, ClientResponseError):
                meta = None

        embed.add_field(name='Uptime', value=self.bot.uptime)
        if meta:
            embed.add_field(name='Instances', value=meta['instances'])
        else:
            embed.add_field(name='Latency',
                            value=f'{self.bot.latency * 1000:.2f} ms')

        embed.add_field(name='Version',
                        value=f'[`{self.bot.version}`]'
                        '(https://modmail.tk/changelog)')
        embed.add_field(name='Author',
                        value='[`kyb3r`](https://github.com/kyb3r)')

        footer = f'Bot ID: {self.bot.user.id}'

        if meta:
            if self.bot.version != meta['latest_version']:
                footer = ("A newer version is available "
                          f"v{meta['latest_version']}")
            else:
                footer = 'You are up to date with the latest version.'

        embed.add_field(name='GitHub',
                        value='https://github.com/kyb3r/modmail',
                        inline=False)

        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    @commands.group()
    @commands.is_owner()
    @trigger_typing
    async def debug(self, ctx):
        """Shows the recent logs of the bot."""

        if ctx.invoked_subcommand is not None:
            return

        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '../temp/logs.log'), 'r+') as f:
            logs = f.read().strip()

        if not logs:
            embed = Embed(
                color=self.bot.main_color,
                title='Debug Logs:',
                description='You don\'t have any logs at the moment.'
            )
            embed.set_footer(text='Go to Heroku to see your logs.')
            return await ctx.send(embed=embed)

        messages = []

        # Using Scala formatting because it's similar to Python for exceptions
        # and it does a fine job formatting the logs.
        msg = '```Scala\n'

        for line in logs.splitlines(keepends=True):
            if msg != '```Scala\n':
                if len(line) + len(msg) + 3 > 2000:
                    msg += '```'
                    messages.append(msg)
                    msg = '```Scala\n'
            msg += line
            if len(msg) + 3 > 2000:
                msg = msg[:1993] + '[...]```'
                messages.append(msg)
                msg = '```Scala\n'

        if msg != '```Scala\n':
            msg += '```'
            messages.append(msg)

        embed = Embed(
            color=self.bot.main_color
        )
        embed.set_footer(text='Debug logs - Navigate using the reactions below.')

        session = MessagePaginatorSession(ctx, *messages, embed=embed)
        return await session.run()

    @debug.command()
    @commands.is_owner()
    @trigger_typing
    async def hastebin(self, ctx):
        """Upload logs to hastebin."""
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '../temp/logs.log'), 'r+') as f:
            logs = f.read().strip()

        try:
            async with self.bot.session.post('https://hastebin.com/documents',
                                             data=logs) as resp:
                key = (await resp.json())["key"]
                embed = Embed(
                    title='Debug Logs',
                    color=self.bot.main_color,
                    description=f'https://hastebin.com/' + key
                )
        except (JSONDecodeError, ClientResponseError, IndexError):
            embed = Embed(
                title='Debug Logs',
                color=self.bot.main_color,
                description='Something\'s wrong. '
                            'We\'re unable to upload your logs to hastebin.'
            )
            embed.set_footer(text='Go to Heroku to see your logs.')
        await ctx.send(embed=embed)

    @debug.command()
    @commands.is_owner()
    @trigger_typing
    async def clear(self, ctx):
        """Clears the locally cached logs."""
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '../temp/logs.log'), 'w'):
            pass
        await ctx.send(embed=Embed(
            color=self.bot.main_color,
            description='Cached logs are now cleared.'
        ))

    @commands.command()
    @commands.is_owner()
    @github_access_token_required
    @trigger_typing
    async def github(self, ctx):
        """Shows the GitHub user your access token is linked to."""
        if ctx.invoked_subcommand:
            return

        data = await self.bot.api.get_user_info()

        embed = Embed(
            title='GitHub',
            description='Current User',
            color=self.bot.main_color
        )
        user = data['user']
        embed.set_author(name=user['username'],
                         icon_url=user['avatar_url'],
                         url=user['url'])
        embed.set_thumbnail(url=user['avatar_url'])
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    @github_access_token_required
    @trigger_typing
    async def update(self, ctx):
        """Updates the bot, this only works with heroku users."""
        metadata = await self.bot.api.get_metadata()

        desc = (f'The latest version is [`{self.bot.version}`]'
                '(https://github.com/kyb3r/modmail/blob/master/bot.py#L25)')

        embed = Embed(
            title='Already up to date',
            description=desc,
            color=self.bot.main_color
        )

        if metadata['latest_version'] == self.bot.version:
            data = await self.bot.api.get_user_info()
            if not data.get('error'):
                user = data['user']
                embed.set_author(name=user['username'],
                                 icon_url=user['avatar_url'],
                                 url=user['url'])
        else:
            data = await self.bot.api.update_repository()

            commit_data = data['data']
            user = data['user']
            embed.title = None
            embed.set_author(name=user['username'],
                             icon_url=user['avatar_url'],
                             url=user['url'])
            embed.set_footer(text=f'Updating Modmail v{self.bot.version} '
                                  f"-> v{metadata['latest_version']}")

            if commit_data:
                embed.set_author(name=user['username'] + ' - Updating bot',
                                 icon_url=user['avatar_url'],
                                 url=user['url'])
                changelog = await Changelog.from_url(self.bot)
                latest = changelog.latest_version
                embed.description = latest.description
                for name, value in latest.fields.items():
                    embed.add_field(name=name, value=value)
                # message = commit_data['commit']['message']
                html_url = commit_data["html_url"]
                short_sha = commit_data['sha'][:6]
                embed.add_field(name='Merge Commit',
                                value=f'[`{short_sha}`]({html_url})')
            else:
                embed.description = ('Already up to date '
                                     'with master repository.')

        return await ctx.send(embed=embed)

    @commands.command(aliases=['presence'])
    @checks.has_permissions(administrator=True)
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

        When activity type is set to `listening`,
        it must be followed by a "to": "listening to..."
        """
        if activity_type == 'clear':
            self.bot.config['activity_type'] = None
            self.bot.config['activity_message'] = None
            await self.bot.config.update()
            await self.set_presence(log=False)
            embed = Embed(
                title='Activity Removed',
                color=self.bot.main_color
            )
            return await ctx.send(embed=embed)

        if not message:
            raise commands.UserInputError

        try:
            activity, msg = (await self.set_presence(
                activity_identifier=activity_type,
                activity_by_key=True,
                activity_message=message,
                log=False
            ))['activity']
        except ValueError:
            raise commands.UserInputError

        self.bot.config['activity_type'] = activity.type.value
        self.bot.config['activity_message'] = message
        await self.bot.config.update()

        embed = Embed(
            title='Activity Changed',
            description=msg,
            color=self.bot.main_color
        )
        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(administrator=True)
    async def status(self, ctx, *, status_type: str):
        """
        Set a custom status for the bot.

        Possible status types:
            - `online`
            - `idle`
            - `dnd`
            - `do_not_disturb` or `do not disturb`
            - `invisible` or `offline`
            - `clear`

        When status type is set to `clear`, the current status is removed.
        """
        if status_type == 'clear':
            self.bot.config['status'] = None
            await self.bot.config.update()
            await self.set_presence(log=False)
            embed = Embed(
                title='Status Removed',
                color=self.bot.main_color
            )
            return await ctx.send(embed=embed)
        status_type = status_type.replace(' ', '_')

        try:
            status, msg = (await self.set_presence(
                status_identifier=status_type,
                status_by_key=True,
                log=False
            ))['status']
        except ValueError:
            raise commands.UserInputError

        self.bot.config['status'] = status.value
        await self.bot.config.update()

        embed = Embed(
            title='Status Changed',
            description=msg,
            color=self.bot.main_color
        )
        return await ctx.send(embed=embed)

    async def set_presence(self, *,
                           status_identifier=None,
                           status_by_key=True,
                           activity_identifier=None,
                           activity_by_key=True,
                           activity_message=None,
                           log=True):

        activity = status = None
        if status_identifier is None:
            status_identifier = self.bot.config.get('status', None)
            status_by_key = False

        try:
            if status_by_key:
                status = Status[status_identifier]
            else:
                status = Status(status_identifier)
        except (KeyError, ValueError):
            if status_identifier is not None:
                msg = f'Invalid status type: {status_identifier}'
                if log:
                    logger.warning(error(msg))
                else:
                    raise ValueError(msg)

        if activity_identifier is None:
            if activity_message is not None:
                raise ValueError('activity_message must be None '
                                 'if activity_identifier is None.')
            activity_identifier = self.bot.config.get('activity_type', None)
            activity_by_key = False

        try:
            if activity_by_key:
                activity_type = ActivityType[activity_identifier]
            else:
                activity_type = ActivityType(activity_identifier)
        except (KeyError, ValueError):
            if activity_identifier is not None:
                msg = f'Invalid activity type: {activity_identifier}'
                if log:
                    logger.warning(error(msg))
                else:
                    raise ValueError(msg)
        else:
            url = None
            activity_message = (
                    activity_message or
                    self.bot.config.get('activity_message', '')
            ).strip()

            if activity_type == ActivityType.listening:
                if activity_message.lower().startswith('to '):
                    # The actual message is after listening to [...]
                    # discord automatically add the "to"
                    activity_message = activity_message[3:].strip()
            elif activity_type == ActivityType.streaming:
                url = self.bot.config.get(
                    'twitch_url', 'https://www.twitch.tv/discord-modmail/'
                )

            if activity_message:
                activity = Activity(type=activity_type,
                                    name=activity_message,
                                    url=url)
            else:
                msg = 'You must supply an activity message to use custom activity.'
                if log:
                    logger.warning(error(msg))
                else:
                    raise ValueError(msg)

        await self.bot.change_presence(activity=activity, status=status)

        presence = {'activity': (None, 'No activity has been set.'),
                    'status': (None, 'No status has been set.')}
        if activity is not None:
            # TODO: Trim message
            to = 'to ' if activity.type == ActivityType.listening else ''
            msg = f'Activity set to: {activity.type.name.capitalize()} '
            msg += f'{to}{activity.name}.'
            presence['activity'] = (activity, msg)
        if status is not None:
            msg = f'Status set to: {status.value}.'
            presence['status'] = (status, msg)
        return presence

    async def on_ready(self):
        # Wait until config cache is populated with stuff from db
        await self.bot.config.wait_until_ready()
        presence = await self.set_presence()
        logger.info(info(presence['activity'][1]))
        logger.info(info(presence['status'][1]))

    @commands.command()
    @trigger_typing
    @checks.has_permissions(administrator=True)
    async def ping(self, ctx):
        """Pong! Returns your websocket latency."""
        embed = Embed(
            title='Pong! Websocket Latency:',
            description=f'{self.bot.ws.latency * 1000:.4f} ms',
            color=self.bot.main_color
        )
        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(administrator=True)
    async def mention(self, ctx, *, mention=None):
        """Changes what the bot mentions at the start of each thread."""
        current = self.bot.config.get('mention', '@here')

        if mention is None:
            embed = Embed(
                title='Current text',
                color=self.bot.main_color,
                description=f'{current}'
            )

        else:
            embed = Embed(
                title='Changed mention!',
                description=f'On thread creation the bot now says {mention}',
                color=self.bot.main_color
            )
            self.bot.config['mention'] = mention
            await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(administrator=True)
    async def prefix(self, ctx, *, prefix=None):
        """Changes the prefix for the bot."""

        current = self.bot.prefix
        embed = Embed(
            title='Current prefix',
            color=self.bot.main_color,
            description=f'{current}'
        )

        if prefix is None:
            await ctx.send(embed=embed)
        else:
            embed.title = 'Changed prefix!'
            embed.description = f'Set prefix to `{prefix}`'
            self.bot.config['prefix'] = prefix
            await self.bot.config.update()
            await ctx.send(embed=embed)

    @commands.group()
    @commands.is_owner()
    async def config(self, ctx):
        """Change config vars for the bot."""

        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command('help')
            await ctx.invoke(cmd, command='config')

    @config.command()
    @commands.is_owner()
    async def options(self, ctx):
        """Return a list of valid config keys you can change."""
        allowed = self.bot.config.allowed_to_change_in_command
        valid = ', '.join(f'`{k}`' for k in allowed)
        embed = Embed(title='Valid Keys',
                      description=valid,
                      color=self.bot.main_color)
        return await ctx.send(embed=embed)

    @config.command()
    @commands.is_owner()
    async def set(self, ctx, key: str.lower, *, value):
        """
        Sets a configuration variable and its value
        """

        keys = self.bot.config.allowed_to_change_in_command

        if key in keys:
            try:
                value, value_text = self.bot.config.clean_data(key, value)
            except InvalidConfigError as exc:
                embed = exc.embed
            else:
                await self.bot.config.update({key: value})
                embed = Embed(
                    title='Success',
                    color=self.bot.main_color,
                    description=f'Set `{key}` to `{value_text}`'
                )
        else:
            embed = Embed(
                title='Error',
                color=Color.red(),
                description=f'{key} is an invalid key.'
            )
            valid_keys = [f'`{k}`' for k in keys]
            embed.add_field(name='Valid keys', value=', '.join(valid_keys))

        return await ctx.send(embed=embed)

    @config.command(name='del')
    @commands.is_owner()
    async def del_config(self, ctx, key: str.lower):
        """Deletes a key from the config."""
        keys = self.bot.config.allowed_to_change_in_command
        if key in keys:
            try:
                del self.bot.config.cache[key]
                await self.bot.config.update()
            except KeyError:
                # when no values were set
                pass
            embed = Embed(
                title='Success',
                color=self.bot.main_color,
                description=f'`{key}` had been deleted from the config.'
            )
        else:
            embed = Embed(
                title='Error',
                color=Color.red(),
                description=f'{key} is an invalid key.'
            )
            valid_keys = [f'`{k}`' for k in keys]
            embed.add_field(name='Valid keys', value=', '.join(valid_keys))

        return await ctx.send(embed=embed)

    @config.command()
    @commands.is_owner()
    async def get(self, ctx, key=None):
        """Shows the config variables that are currently set."""
        keys = self.bot.config.allowed_to_change_in_command

        if key:
            if key in keys:
                desc = f'`{key}` is set to `{self.bot.config.get(key)}`'
                embed = Embed(
                    color=self.bot.main_color,
                    description=desc
                )
                embed.set_author(name='Config variable',
                                 icon_url=self.bot.user.avatar_url)

            else:
                embed = Embed(
                    title='Error',
                    color=Color.red(),
                    description=f'`{key}` is an invalid key.'
                )
                valid_keys = [f'`{k}`' for k in keys]
                embed.add_field(name='Valid keys', value=', '.join(valid_keys))

        else:
            embed = Embed(
                color=self.bot.main_color,
                description='Here is a list of currently '
                            'set configuration variables.'
            )
            embed.set_author(name='Current config',
                             icon_url=self.bot.user.avatar_url)

            config = {
                k: v for k, v in self.bot.config.cache.items()
                if v and k in keys
            }

            for k, v in reversed(list(config.items())):
                embed.add_field(name=k, value=f'`{v}`', inline=False)

        return await ctx.send(embed=embed)

    @commands.group(aliases=['aliases'])
    @checks.has_permissions(manage_messages=True)
    async def alias(self, ctx):
        """Returns a list of aliases that are currently set."""
        if ctx.invoked_subcommand is not None:
            return

        embeds = []
        desc = 'Here is a list of aliases that are currently configured.'

        if self.bot.aliases:
            embed = Embed(
                color=self.bot.main_color,
                description=desc
            )
        else:
            embed = Embed(
                color=self.bot.main_color,
                description='You dont have any aliases at the moment.'
            )
        embed.set_author(name='Command aliases', icon_url=ctx.guild.icon_url)
        embed.set_footer(text=f'Do {self.bot.prefix}'
                              'help aliases for more commands.')
        embeds.append(embed)

        for name, value in self.bot.aliases.items():
            if len(embed.fields) == 5:
                embed = Embed(color=self.bot.main_color, description=desc)
                embed.set_author(name='Command aliases',
                                 icon_url=ctx.guild.icon_url)
                embed.set_footer(text=f'Do {self.bot.prefix}help '
                                      'aliases for more commands.')

                embeds.append(embed)
            embed.add_field(name=name, value=value, inline=False)

        session = PaginatorSession(ctx, *embeds)
        return await session.run()

    @alias.command(name='add')
    @checks.has_permissions(manage_messages=True)
    async def add_(self, ctx, name: str.lower, *, value):
        """Add an alias to the bot config."""
        if 'aliases' not in self.bot.config.cache:
            self.bot.config['aliases'] = {}

        if self.bot.get_command(name) or self.bot.config.aliases.get(name):
            embed = Embed(
                title='Error',
                color=Color.red(),
                description='A command or alias already exists '
                f'with the same name: `{name}`.'
            )
            return await ctx.send(embed=embed)

        if not self.bot.get_command(value.split()[0]):
            embed = Embed(
                title='Error',
                color=Color.red(),
                description='The command you are attempting to point '
                f'to does not exist: `{value.split()[0]}`.'
            )
            return await ctx.send(embed=embed)

        self.bot.config.aliases[name] = value
        await self.bot.config.update()

        embed = Embed(
            title='Added alias',
            color=self.bot.main_color,
            description=f'`{name}` points to: {value}'
        )

        return await ctx.send(embed=embed)

    @alias.command(name='del')
    @checks.has_permissions(manage_messages=True)
    async def del_alias(self, ctx, *, name: str.lower):
        """Removes a alias from bot config."""

        if 'aliases' not in self.bot.config.cache:
            self.bot.config['aliases'] = {}

        if self.bot.config.aliases.get(name):
            del self.bot.config['aliases'][name]
            await self.bot.config.update()

            embed = Embed(
                title='Removed alias',
                color=self.bot.main_color,
                description=f'`{name}` no longer exists.'
            )

        else:
            embed = Embed(
                title='Error',
                color=Color.red(),
                description=f'Alias `{name}` does not exist.'
            )

        return await ctx.send(embed=embed)

    @commands.command(hidden=True, name='eval')
    @commands.is_owner()
    async def eval_(self, ctx, *, body):
        """Evaluates Python code"""

        env = {
            'ctx': ctx,
            'bot': self.bot,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            'source': inspect.getsource,
            'discord': __import__('discord')
        }

        env.update(globals())

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
            exec(to_compile, env)  # pylint: disable=exec-used
        except Exception as exc:  # pylint: disable=broad-except
            await ctx.send(f'```py\n{exc.__class__.__name__}: {exc}\n```')
            return await ctx.message.add_reaction('\u2049')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:  # pylint: disable=broad-except
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
            return await ctx.message.add_reaction('\u2049')

        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        await ctx.send(f'```py\n{value}\n```')
                    except Exception:  # pylint: disable=broad-except
                        paginated_text = paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                await ctx.send(f'```py\n{page}\n```')
                                break
                            await ctx.send(f'```py\n{page}\n```')
            else:
                try:
                    await ctx.send(f'```py\n{value}{ret}\n```')
                except Exception:  # pylint: disable=broad-except
                    paginated_text = paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            await ctx.send(f'```py\n{page}\n```')
                            break
                        await ctx.send(f'```py\n{page}\n```')


def setup(bot):
    bot.add_cog(Utility(bot))
