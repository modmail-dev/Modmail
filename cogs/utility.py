import inspect
import logging
import os
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from difflib import get_close_matches
from io import StringIO
from operator import itemgetter
from typing import Union
from json import JSONDecodeError
from pkg_resources import parse_version
from textwrap import indent

from discord import Embed, Color, Activity, Role, Member
from discord.enums import ActivityType, Status
from discord.ext import commands

from aiohttp import ClientResponseError

from core import checks
from core.changelog import Changelog
from core.decorators import github_access_token_required, trigger_typing
from core.models import Bot, InvalidConfigError, PermissionLevel
from core.paginator import PaginatorSession, MessagePaginatorSession
from core.utils import cleanup_code, info, error, User, get_perm_level

logger = logging.getLogger('Modmail')


class Utility:
    """General commands that provide utility."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def format_cog_help(self, ctx, cog):
        """Formats the text for a cog help"""

        prefix = self.bot.prefix

        fmts = ['']
        for perm_level, cmd in sorted(((get_perm_level(c), c) for c in self.bot.commands),
                                      key=itemgetter(0)):
            if cmd.instance is cog and not cmd.hidden:
                if perm_level is PermissionLevel.INVALID:
                    new_fmt = f'`{prefix + cmd.qualified_name}` '
                else:
                    new_fmt = f'`[{perm_level}] {prefix + cmd.qualified_name}` '

                new_fmt += f'- {cmd.short_doc}\n'
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

            continued = ' (Continued)' if len(embeds) > 0 else ''

            embed.set_author(name=cog.__class__.__name__ + ' - Help' + continued,
                             icon_url=ctx.bot.user.avatar_url)

            embed.set_footer(text=f'Type "{prefix}help command" '
                                  'for more info on a command.')
            embeds.append(embed)
            
        return embeds

    async def format_command_help(self, cmd):
        """Formats command help."""
        if cmd.hidden:
            return None

        prefix = self.bot.prefix

        perm_level = get_perm_level(cmd)
        if perm_level is not PermissionLevel.INVALID:
            perm_level = f'{perm_level.name} [{perm_level}]'
        else:
            perm_level = ''

        embed = Embed(
            title=f'`{prefix}{cmd.signature}`',
            color=self.bot.main_color,
            description=cmd.help
        )

        if not isinstance(cmd, commands.Group):
            embed.set_footer(text=f'Permission level: {perm_level}')
            return embed
        
        embed.add_field(name='Permission level', value=perm_level)

        fmt = ''
        length = len(cmd.commands)
        for i, c in enumerate(sorted(cmd.commands, key=lambda c: c.name)):
            # Bug: fmt may run over the embed limit
            if length == i + 1:  # last
                branch = '└─'
            else:
                branch = '├─'
            fmt += f'`{branch} {c.name}` - {c.short_doc}\n'

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

        for name, c in self.bot.all_commands.items():
            if not c.hidden:
                choices.add(name)

        closest = get_close_matches(command, choices, n=1, cutoff=0.75)
        if closest:
            # Perhaps you meant:
            #  - `item`
            embed.description = (f'**Perhaps you meant:**\n'
                                 f'\u2000- `{closest[0]}`')
        return embed

    @commands.command(name='help')
    @checks.has_permissions(PermissionLevel.REGULAR)
    @trigger_typing
    async def help_(self, ctx, *, command: str = None):
        """Shows the help message."""

        if command:
            cmd = self.bot.get_command(command)
            cog = self.bot.cogs.get(command)
            embeds = []

            if cmd:
                help_msg = await self.format_command_help(cmd)
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
    @checks.has_permissions(PermissionLevel.REGULAR)
    @trigger_typing
    async def changelog(self, ctx):
        """Show a paginated changelog of the bot."""
        changelog = await Changelog.from_url(self.bot)
        try:
            paginator = PaginatorSession(ctx, *changelog.embeds)
            await paginator.run()
        except:
            await ctx.send(changelog.CHANGELOG_URL)

    @commands.command(aliases=['bot', 'info'])
    @checks.has_permissions(PermissionLevel.REGULAR)
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

        embed.add_field(name='Uptime', value=self.bot.uptime)
        embed.add_field(name='Latency', value=f'{self.bot.latency * 1000:.2f} ms')

        embed.add_field(name='Version',
                        value=f'`{self.bot.version}`')
        embed.add_field(name='Author',
                        value='[`kyb3r`](https://github.com/kyb3r)')

        footer = f'Bot ID: {self.bot.user.id}'

        changelog = await Changelog.from_url(self.bot)
        latest = changelog.latest_version

        if parse_version(self.bot.version) < parse_version(latest.version):
            footer = f"A newer version is available v{latest.version}"
        else:
            footer = 'You are up to date with the latest version.'

        embed.add_field(name='GitHub',
                        value='https://github.com/kyb3r/modmail',
                        inline=False)

        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    @trigger_typing
    async def debug(self, ctx):
        """Shows the recent logs of the bot."""

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
    @checks.has_permissions(PermissionLevel.OWNER)
    @trigger_typing
    async def hastebin(self, ctx):
        """Upload logs to hastebin."""

        haste_url = os.environ.get('HASTE_URL', 'https://hasteb.in')

        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '../temp/logs.log'), 'r+') as f:
            logs = f.read().strip()

        try:
            async with self.bot.session.post(haste_url + '/documents',
                                             data=logs) as resp:
                key = (await resp.json())["key"]
                embed = Embed(
                    title='Debug Logs',
                    color=self.bot.main_color,
                    description=f'{haste_url}/' + key
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
    @checks.has_permissions(PermissionLevel.OWNER)
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
    @checks.has_permissions(PermissionLevel.OWNER)
    @github_access_token_required
    @trigger_typing
    async def github(self, ctx):
        """Shows the GitHub user your access token is linked to."""
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
    @checks.has_permissions(PermissionLevel.OWNER)
    @github_access_token_required
    @trigger_typing
    async def update(self, ctx, *, flag: str = ''):
        """Updates the bot, this only works with heroku users.

        To stay up-to-date with the latest commit from GitHub, specify "force" as the flag.
        """

        changelog = await Changelog.from_url(self.bot)
        latest = changelog.latest_version

        desc = (f'The latest version is [`{self.bot.version}`]'
                '(https://github.com/kyb3r/modmail/blob/master/bot.py#L25)')

        if parse_version(self.bot.version) >= parse_version(latest.version) and flag.lower() != 'force':
            embed = Embed(
                title='Already up to date',
                description=desc,
                color=self.bot.main_color
            )

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

            if commit_data:
                embed = Embed(color=self.bot.main_color)

                embed.set_footer(text=f'Updating Modmail v{self.bot.version} '
                                      f'-> v{latest.version}')

                embed.set_author(name=user['username'] + ' - Updating bot',
                                 icon_url=user['avatar_url'],
                                 url=user['url'])

                embed.description = latest.description
                for name, value in latest.fields.items():
                    embed.add_field(name=name, value=value)
                # message = commit_data['commit']['message']
                html_url = commit_data["html_url"]
                short_sha = commit_data['sha'][:6]
                embed.add_field(name='Merge Commit',
                                value=f'[`{short_sha}`]({html_url})')
            else:
                embed = Embed(
                    title='Already up to date with master repository.',
                    description='No further updates required',
                    color=self.bot.main_color
                )
                embed.set_author(name=user['username'],
                                 icon_url=user['avatar_url'],
                                 url=user['url'])

        return await ctx.send(embed=embed)

    @commands.command(aliases=['presence'])
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def activity(self, ctx, activity_type: str.lower, *, message: str = ''):
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
            await self.set_presence()
            embed = Embed(
                title='Activity Removed',
                color=self.bot.main_color
            )
            return await ctx.send(embed=embed)

        if not message:
            raise commands.UserInputError

        activity, msg = (await self.set_presence(
            activity_identifier=activity_type,
            activity_by_key=True,
            activity_message=message
        ))['activity']
        if activity is None:
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
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def status(self, ctx, *, status_type: str.lower):
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
            await self.set_presence()
            embed = Embed(
                title='Status Removed',
                color=self.bot.main_color
            )
            return await ctx.send(embed=embed)
        status_type = status_type.replace(' ', '_')

        status, msg = (await self.set_presence(
            status_identifier=status_type,
            status_by_key=True
        ))['status']
        if status is None:
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
                           activity_message=None):

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
                logger.warning(error(msg))

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
                logger.warning(error(msg))
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
                logger.warning(error(msg))

        await self.bot.change_presence(activity=activity, status=status)

        presence = {'activity': (None, 'No activity has been set.'),
                    'status': (None, 'No status has been set.')}
        if activity is not None:
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
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @trigger_typing
    async def ping(self, ctx):
        """Pong! Returns your websocket latency."""
        embed = Embed(
            title='Pong! Websocket Latency:',
            description=f'{self.bot.ws.latency * 1000:.4f} ms',
            color=self.bot.main_color
        )
        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
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
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
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

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config(self, ctx):
        """Change config vars for the bot."""
        cmd = self.bot.get_command('help')
        await ctx.invoke(cmd, command='config')

    @config.command()
    @checks.has_permissions(PermissionLevel.OWNER)
    async def options(self, ctx):
        """Return a list of valid config keys you can change."""
        allowed = self.bot.config.allowed_to_change_in_command
        valid = ', '.join(f'`{k}`' for k in allowed)
        embed = Embed(title='Valid Keys',
                      description=valid,
                      color=self.bot.main_color)
        return await ctx.send(embed=embed)

    @config.command()
    @checks.has_permissions(PermissionLevel.OWNER)
    async def set(self, ctx, key: str.lower, *, value):
        """
        Sets a configuration variable and its value
        """

        keys = self.bot.config.allowed_to_change_in_command

        if key in keys:
            try:
                value, value_text = await self.bot.config.clean_data(key, value)
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

    @config.command(name='remove', aliases=['del', 'delete', 'rm'])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def remove_config(self, ctx, key: str.lower):
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
    @checks.has_permissions(PermissionLevel.OWNER)
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

    @commands.group(aliases=['aliases'], invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def alias(self, ctx):
        """Returns a list of aliases that are currently set."""

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
    @checks.has_permissions(PermissionLevel.MODERATOR)
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

    @alias.command(name='remove', aliases=['del', 'delete', 'rm'])
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def remove_alias(self, ctx, *, name: str.lower):
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

    @commands.group(aliases=['perms'], invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions(self, ctx):
        """Sets the permissions for Modmail commands.

        You may set permissions based on individual command names, or permission
        levels.

        Acceptable permission levels are:
            - **Owner** [5] (absolute control over the bot)
            - **Administrator** [4] (administrative powers such as setting activities)
            - **Moderator** [3] (ability to block)
            - **Supporter** [2] (access to core Modmail supporting functions)
            - **Regular** [1] (most basic interactions such as help and about)

        By default, owner is set to the bot owner and regular is @everyone.

        Note: You will still have to manually give/take permission to the Modmail
        category to users/roles.
        """
        cmd = self.bot.get_command('help')
        await ctx.invoke(cmd, command='perms')

    @permissions.group(name='add', invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def add_perms(self, ctx):
        """Add a permission to a command or a permission level."""
        cmd = self.bot.get_command('help')
        await ctx.invoke(cmd, command='perms add')

    @add_perms.command(name='command')
    @checks.has_permissions(PermissionLevel.OWNER)
    async def add_perms_command(self, ctx, command: str, *, user_or_role: Union[User, Role, str]):
        """Add a user, role, or everyone permission to use a command."""
        if command not in self.bot.all_commands:
            embed = Embed(
                title='Error',
                color=Color.red(),
                description='The command you are attempting to point '
                            f'to does not exist: `{command}`.'
            )
            return await ctx.send(embed=embed)

        if hasattr(user_or_role, 'id'):
            value = user_or_role.id
        elif user_or_role in {'everyone', 'all'}:
            value = -1
        else:
            raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

        await self.bot.update_perms(self.bot.all_commands[command].name, value)
        embed = Embed(
            title='Success',
            color=self.bot.main_color,
            description=f'Permission for {command} was successfully updated.'
        )
        return await ctx.send(embed=embed)

    @add_perms.command(name='level', aliases=['group'])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def add_perms_level(self, ctx, level: str, *, user_or_role: Union[User, Role, str]):
        """Add a user, role, or everyone permission to use commands of a permission level."""
        if level.upper() not in PermissionLevel.__members__:
            embed = Embed(
                title='Error',
                color=Color.red(),
                description='The permission level you are attempting to point '
                            f'to does not exist: `{level}`.'
            )
            return await ctx.send(embed=embed)

        if hasattr(user_or_role, 'id'):
            value = user_or_role.id
        elif user_or_role in {'everyone', 'all'}:
            value = -1
        else:
            raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

        await self.bot.update_perms(PermissionLevel[level.upper()], value)
        embed = Embed(
            title='Success',
            color=self.bot.main_color,
            description=f'Permission for {level} was successfully updated.'
        )
        return await ctx.send(embed=embed)

    @permissions.group(name='remove', aliases=['del', 'delete', 'rm', 'revoke'],
                       invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def remove_perms(self, ctx):
        """Remove a permission to use a command or permission level."""
        cmd = self.bot.get_command('help')
        await ctx.invoke(cmd, command='perms remove')

    @remove_perms.command(name='command')
    @checks.has_permissions(PermissionLevel.OWNER)
    async def remove_perms_command(self, ctx, command: str, *, user_or_role: Union[User, Role, str]):
        """Remove a user, role, or everyone permission to use a command."""
        if command not in self.bot.all_commands:
            embed = Embed(
                title='Error',
                color=Color.red(),
                description='The command you are attempting to point '
                            f'to does not exist: `{command}`.'
            )
            return await ctx.send(embed=embed)

        if hasattr(user_or_role, 'id'):
            value = user_or_role.id
        elif user_or_role in {'everyone', 'all'}:
            value = -1
        else:
            raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

        await self.bot.update_perms(self.bot.all_commands[command].name, value, add=False)
        embed = Embed(
            title='Success',
            color=self.bot.main_color,
            description=f'Permission for {command} was successfully updated.'
        )
        return await ctx.send(embed=embed)

    @remove_perms.command(name='level', aliases=['group'])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def remove_perms_level(self, ctx, level: str, *, user_or_role: Union[User, Role, str]):
        """Remove a user, role, or everyone permission to use commands of a permission level."""
        if level.upper() not in PermissionLevel.__members__:
            embed = Embed(
                title='Error',
                color=Color.red(),
                description='The permission level you are attempting to point '
                f'to does not exist: `{level}`.'
            )
            return await ctx.send(embed=embed)

        if hasattr(user_or_role, 'id'):
            value = user_or_role.id
        elif user_or_role in {'everyone', 'all'}:
            value = -1
        else:
            raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

        await self.bot.update_perms(PermissionLevel[level.upper()], value, add=False)
        embed = Embed(
            title='Success',
            color=self.bot.main_color,
            description=f'Permission for {level} was successfully updated.'
        )
        return await ctx.send(embed=embed)

    @permissions.group(name='get', invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def get_perms(self, ctx, *, user_or_role: Union[User, Role, str]):
        """View the currently-set permissions."""

        if hasattr(user_or_role, 'id'):
            value = user_or_role.id
        elif user_or_role in {'everyone', 'all'}:
            value = -1
        else:
            raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

        cmds = []
        levels = []
        for cmd in self.bot.commands:
            permissions = self.bot.config.command_permissions.get(cmd.name, [])
            if value in permissions:
                cmds.append(cmd.name)
        for level in PermissionLevel:
            permissions = self.bot.config.level_permissions.get(level.name, [])
            if value in permissions:
                levels.append(level.name)
        mention = user_or_role.name if hasattr(user_or_role, 'name') else user_or_role
        desc_cmd = ', '.join(map(lambda x: f'`{x}`', cmds)) if cmds else 'No permission entries found.'
        desc_level = ', '.join(map(lambda x: f'`{x}`', levels)) if levels else 'No permission entries found.'

        embeds = [
            Embed(
                title=f'{mention} has permission with the following commands:',
                description=desc_cmd,
                color=self.bot.main_color
            ),
            Embed(
                title=f'{mention} has permission with the following permission groups:',
                description=desc_level,
                color=self.bot.main_color
            )
        ]
        p_session = PaginatorSession(ctx, *embeds)
        return await p_session.run()

    @get_perms.command(name='command')
    @checks.has_permissions(PermissionLevel.OWNER)
    async def get_perms_command(self, ctx, *, command: str = None):
        """View the currently-set permissions for a command."""

        def get_command(cmd):
            permissions = self.bot.config.command_permissions.get(cmd.name, [])
            if not permissions:
                embed = Embed(
                    title=f'Permission entries for command `{cmd.name}`:',
                    description='No permission entries found.',
                    color=self.bot.main_color,
                )
            else:
                values = []
                for perm in permissions:
                    if perm == -1:
                        values.insert(0, '**everyone**')
                        continue
                    member = ctx.guild.get_member(perm)
                    if member is not None:
                        values.append(member.mention)
                        continue
                    user = self.bot.get_user(perm)
                    if user is not None:
                        values.append(user.mention)
                        continue
                    role = ctx.guild.get_role(perm)
                    if role is not None:
                        values.append(role.mention)
                    else:
                        values.append(str(perm))

                embed = Embed(
                    title=f'Permission entries for command `{cmd.name}`:',
                    description=', '.join(values),
                    color=self.bot.main_color
                )
            return embed

        embeds = []
        if command is not None:
            if command not in self.bot.all_commands:
                embed = Embed(
                    title='Error',
                    color=Color.red(),
                    description='The command you are attempting to point '
                    f'to does not exist: `{command}`.'
                )
                return await ctx.send(embed=embed)
            embeds.append(get_command(self.bot.all_commands[command]))
        else:
            for cmd in self.bot.commands:
                embeds.append(get_command(cmd))

        p_session = PaginatorSession(ctx, *embeds)
        return await p_session.run()

    @get_perms.command(name='level', aliases=['group'])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def get_perms_level(self, ctx, *, level: str = None):
        """View the currently-set permissions for commands of a permission level."""

        def get_level(perm_level):
            permissions = self.bot.config.level_permissions.get(perm_level.name, [])
            if not permissions:
                embed = Embed(
                    title='Permission entries for permission '
                          f'level `{perm_level.name}`:',
                    description='No permission entries found.',
                    color=self.bot.main_color,
                )
            else:
                values = []
                for perm in permissions:
                    if perm == -1:
                        values.insert(0, '**everyone**')
                        continue
                    member = ctx.guild.get_member(perm)
                    if member is not None:
                        values.append(member.mention)
                        continue
                    user = self.bot.get_user(perm)
                    if user is not None:
                        values.append(user.mention)
                        continue
                    role = ctx.guild.get_role(perm)
                    if role is not None:
                        values.append(role.mention)
                    else:
                        values.append(str(perm))

                embed = Embed(
                    title=f'Permission entries for permission level `{perm_level.name}`:',
                    description=', '.join(values),
                    color=self.bot.main_color,
                )
            return embed

        embeds = []
        if level is not None:
            if level.upper() not in PermissionLevel.__members__:
                embed = Embed(
                    title='Error',
                    color=Color.red(),
                    description='The permission level you are attempting to point '
                    f'to does not exist: `{level}`.'
                )
                return await ctx.send(embed=embed)
            embeds.append(get_level(PermissionLevel[level.upper()]))
        else:
            for perm_level in PermissionLevel:
                embeds.append(get_level(perm_level))

        p_session = PaginatorSession(ctx, *embeds)
        return await p_session.run()
    
    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def oauth(self, ctx):
        """Commands relating to Logviewer oauth2 login authentication."""
        cmd = self.bot.get_command('help')
        await ctx.invoke(cmd, command='config')
    
    @oauth.command()
    @checks.has_permissions(PermissionLevel.OWNER)
    async def whitelist(self, ctx, target: Union[Member, Role]):
        """Whitelist or un-whitelist a user or role from having access to logs."""
        whitelisted = self.bot.config['oauth_whitelist']

        if target.id in whitelisted:
            whitelisted.remove(target.id)
            removed = True
        else:
            whitelisted.append(target.id)
            removed = False
        
        await self.bot.config.update()

        em = Embed(color=self.bot.main_color)
        em.title = 'Success'
        em.description = (
            f"{'Un-w' if removed else 'W'}hitelisted "
            f"{target.mention} to view logs."
            )

        await ctx.send(embed=em)
    
    @oauth.command()
    @checks.has_permissions(PermissionLevel.OWNER)
    async def get(self, ctx):
        """Shows a list of users and roles that are whitelisted to view logs."""
        whitelisted = self.bot.config['oauth_whitelist']
        
        users = []
        roles = []

        for id in whitelisted:
            user = self.bot.get_user(id)
            if user:
                users.append(user)
            role = self.bot.modmail_guild.get_role(id)
            if role:
                roles.append(role)
        
        em = Embed(color=self.bot.main_color)
        em.title = 'Oauth Whitelist'

        em.add_field(name='Users', value=' '.join(u.mention for u in users) or 'None')
        em.add_field(name='Roles', value=' '.join(r.mention for r in roles) or 'None')

        await ctx.send(embed=em)
        


    @commands.command(hidden=True, name='eval')
    @checks.has_permissions(PermissionLevel.OWNER)
    async def eval_(self, ctx, *, body: str):
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
