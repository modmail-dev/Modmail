import asyncio
import inspect
import logging
import os
import traceback
import random
from contextlib import redirect_stdout
from datetime import datetime
from difflib import get_close_matches
from io import StringIO
from typing import Union
from types import SimpleNamespace as param
from json import JSONDecodeError, loads
from textwrap import indent

from discord import Embed, Color, Activity, Role
from discord.enums import ActivityType, Status
from discord.ext import commands

from aiohttp import ClientResponseError
from pkg_resources import parse_version

from core import checks
from core.changelog import Changelog
from core.decorators import trigger_typing
from core.models import InvalidConfigError, PermissionLevel
from core.paginator import PaginatorSession, MessagePaginatorSession
from core.utils import cleanup_code, info, error, User, get_perm_level

logger = logging.getLogger("Modmail")


class ModmailHelpCommand(commands.HelpCommand):
    async def format_cog_help(self, cog):
        bot = self.context.bot
        prefix = self.clean_prefix

        formats = [""]
        for cmd in await self.filter_commands(
            cog.get_commands(), sort=True, key=get_perm_level
        ):
            perm_level = get_perm_level(cmd)
            if perm_level is PermissionLevel.INVALID:
                format_ = f"`{prefix + cmd.qualified_name}` "
            else:
                format_ = f"`[{perm_level}] {prefix + cmd.qualified_name}` "

            format_ += f"- {cmd.short_doc}\n"
            if not format_.strip():
                continue
            if len(format_) + len(formats[-1]) >= 1024:
                formats.append(format_)
            else:
                formats[-1] += format_

        embeds = []
        for format_ in formats:
            embed = Embed(
                description=f'*{cog.description or "No description."}*',
                color=bot.main_color,
            )

            embed.add_field(name="Commands", value=format_ or "No commands.")

            continued = " (Continued)" if embeds else ""
            embed.set_author(
                name=cog.qualified_name + " - Help" + continued,
                icon_url=bot.user.avatar_url,
            )

            embed.set_footer(
                text=f'Type "{prefix}{self.command_attrs["name"]} command" '
                "for more info on a specific command."
            )
            embeds.append(embed)
        return embeds

    def process_help_msg(self, help_: str):
        return help_.format(prefix=self.clean_prefix) if help_ else "No help message."

    async def send_bot_help(self, cogs):
        embeds = []
        # TODO: Implement for no cog commands

        cogs = list(filter(None, cogs))

        bot = self.context.bot
        
        # always come first
        default_cogs = [ 
            bot.get_cog("Modmail"),
            bot.get_cog("Utility"),
            bot.get_cog("Plugins"),
        ]
        
        default_cogs.extend(c for c in cogs if c not in default_cogs)

        for cog in default_cogs:
            embeds.extend(await self.format_cog_help(cog))

        p_session = PaginatorSession(
            self.context, *embeds, destination=self.get_destination()
        )
        return await p_session.run()

    async def send_cog_help(self, cog):
        embeds = await self.format_cog_help(cog)
        p_session = PaginatorSession(
            self.context, *embeds, destination=self.get_destination()
        )
        return await p_session.run()

    async def send_command_help(self, command):
        if not await self.filter_commands([command]):
            return
        perm_level = get_perm_level(command)
        if perm_level is not PermissionLevel.INVALID:
            perm_level = f"{perm_level.name} [{perm_level}]"
        else:
            perm_level = ""

        embed = Embed(
            title=f"`{self.get_command_signature(command)}`",
            color=self.context.bot.main_color,
            description=self.process_help_msg(command.help),
        )
        embed.set_footer(text=f"Permission level: {perm_level}")
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        if not await self.filter_commands([group]):
            return

        perm_level = get_perm_level(group)
        if perm_level is not PermissionLevel.INVALID:
            perm_level = f"{perm_level.name} [{perm_level}]"
        else:
            perm_level = ""

        embed = Embed(
            title=f"`{self.get_command_signature(group)}`",
            color=self.context.bot.main_color,
            description=self.process_help_msg(group.help),
        )

        if perm_level:
            embed.add_field(name="Permission level", value=perm_level, inline=False)

        format_ = ""
        length = len(group.commands)

        for i, command in enumerate(
            await self.filter_commands(group.commands, sort=True, key=lambda c: c.name)
        ):
            # BUG: fmt may run over the embed limit
            # TODO: paginate this
            if length == i + 1:  # last
                branch = "└─"
            else:
                branch = "├─"
            format_ += f"`{branch} {command.name}` - {command.short_doc}\n"

        embed.add_field(name="Sub Commands", value=format_[:1024], inline=False)
        embed.set_footer(
            text=f'Type "{self.clean_prefix}{self.command_attrs["name"]} command" '
            "for more info on a command."
        )

        await self.get_destination().send(embed=embed)

    async def send_error_message(self, msg):  # pylint: disable=W0221
        logger.warning(error(f"CommandNotFound: {msg}"))

        embed = Embed(color=Color.red())
        embed.set_footer(
            text=f'Command/Category "{self.context.kwargs.get("command")}" not found.'
        )

        choices = set()

        for name, cmd in self.context.bot.all_commands.items():
            if not cmd.hidden:
                choices.add(name)
        command = self.context.kwargs.get("command")
        closest = get_close_matches(command, choices)
        if closest:
            embed.add_field(
                name=f"Perhaps you meant:", value="\n".join(f"`{x}`" for x in closest)
            )
        else:
            embed.title = "Cannot find command or category"
            embed.set_footer(
                text=f'Type "{self.clean_prefix}{self.command_attrs["name"]}" '
                "for a list of all available commands."
            )
        await self.get_destination().send(embed=embed)


class Utility(commands.Cog):
    """General commands that provide utility."""

    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        self.bot.help_command = ModmailHelpCommand(
            verify_checks=False, command_attrs={"help": "Shows this help message."}
        )
        # Looks a bit ugly
        self.bot.help_command._command_impl = checks.has_permissions(
            PermissionLevel.REGULAR
        )(self.bot.help_command._command_impl)

        self.bot.help_command.cog = self

        # Class Variables
        self.presence = None

        # Tasks
        self.presence_task = self.bot.loop.create_task(self.loop_presence())

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

    @commands.command()
    @checks.has_permissions(PermissionLevel.REGULAR)
    @trigger_typing
    async def changelog(self, ctx):
        """Shows the changelog of the Modmail."""
        changelog = await Changelog.from_url(self.bot)
        try:
            paginator = PaginatorSession(ctx, *changelog.embeds)
            await paginator.run()
        except:
            await ctx.send(changelog.CHANGELOG_URL)

    @commands.command(aliases=["bot", "info"])
    @checks.has_permissions(PermissionLevel.REGULAR)
    @trigger_typing
    async def about(self, ctx):
        """Shows information about this bot."""
        embed = Embed(color=self.bot.main_color, timestamp=datetime.utcnow())
        embed.set_author(name="Modmail - About", icon_url=self.bot.user.avatar_url)
        embed.set_thumbnail(url=self.bot.user.avatar_url)

        desc = "This is an open source Discord bot that serves as a means for "
        desc += "members to easily communicate with server administrators in "
        desc += "an organised manner."
        embed.description = desc

        embed.add_field(name="Uptime", value=self.bot.uptime)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.2f} ms")
        embed.add_field(name="Version", value=f"`{self.bot.version}`")
        embed.add_field(name="Author", value="[`kyb3r`](https://github.com/kyb3r)")

        changelog = await Changelog.from_url(self.bot)
        latest = changelog.latest_version

        if parse_version(self.bot.version) < parse_version(latest.version):
            footer = f"A newer version is available v{latest.version}"
        else:
            footer = "You are up to date with the latest version."

        embed.add_field(
            name="GitHub", value="https://github.com/kyb3r/modmail", inline=False
        )

        embed.add_field(name="Donate", value="[Patreon](https://patreon.com/kyber)")

        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.REGULAR)
    @trigger_typing
    async def sponsors(self, ctx):
        """Shows a list of sponsors."""
        resp = await self.bot.session.get(
            "https://raw.githubusercontent.com/kyb3r/modmail/master/SPONSORS.json"
        )
        data = loads(await resp.text())

        embeds = []

        for elem in data:
            em = Embed.from_dict(elem["embed"])
            embeds.append(em)

        random.shuffle(embeds)

        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    @trigger_typing
    async def debug(self, ctx):
        """Shows the recent application-logs of the bot."""

        log_file_name = self.bot.config.token.split(".")[0]

        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"../temp/{log_file_name}.log",
            ),
            "r+",
        ) as f:
            logs = f.read().strip()

        if not logs:
            embed = Embed(
                color=self.bot.main_color,
                title="Debug Logs:",
                description="You don't have any logs at the moment.",
            )
            embed.set_footer(text="Go to Heroku to see your logs.")
            return await ctx.send(embed=embed)

        messages = []

        # Using Scala formatting because it's similar to Python for exceptions
        # and it does a fine job formatting the logs.
        msg = "```Scala\n"

        for line in logs.splitlines(keepends=True):
            if msg != "```Scala\n":
                if len(line) + len(msg) + 3 > 2000:
                    msg += "```"
                    messages.append(msg)
                    msg = "```Scala\n"
            msg += line
            if len(msg) + 3 > 2000:
                msg = msg[:1993] + "[...]```"
                messages.append(msg)
                msg = "```Scala\n"

        if msg != "```Scala\n":
            msg += "```"
            messages.append(msg)

        embed = Embed(color=self.bot.main_color)
        embed.set_footer(text="Debug logs - Navigate using the reactions below.")

        session = MessagePaginatorSession(ctx, *messages, embed=embed)
        session.current = len(messages) - 1
        return await session.run()

    @debug.command(name="hastebin", aliases=["haste"])
    @checks.has_permissions(PermissionLevel.OWNER)
    @trigger_typing
    async def debug_hastebin(self, ctx):
        """Posts application-logs to Hastebin."""

        haste_url = os.environ.get("HASTE_URL", "https://hasteb.in")
        log_file_name = self.bot.config.token.split(".")[0]

        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"../temp/{log_file_name}.log",
            ),
            "r+",
        ) as f:
            logs = f.read().strip()

        try:
            async with self.bot.session.post(
                haste_url + "/documents", data=logs
            ) as resp:
                key = (await resp.json())["key"]
                embed = Embed(
                    title="Debug Logs",
                    color=self.bot.main_color,
                    description=f"{haste_url}/" + key,
                )
        except (JSONDecodeError, ClientResponseError, IndexError):
            embed = Embed(
                title="Debug Logs",
                color=self.bot.main_color,
                description="Something's wrong. "
                "We're unable to upload your logs to hastebin.",
            )
            embed.set_footer(text="Go to Heroku to see your logs.")
        await ctx.send(embed=embed)

    @debug.command(name="clear", aliases=["wipe"])
    @checks.has_permissions(PermissionLevel.OWNER)
    @trigger_typing
    async def debug_clear(self, ctx):
        """Clears the locally cached logs."""

        log_file_name = self.bot.config.token.split(".")[0]

        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"../temp/{log_file_name}.log",
            ),
            "w",
        ):
            pass
        await ctx.send(
            embed=Embed(
                color=self.bot.main_color, description="Cached logs are now cleared."
            )
        )
        
    @commands.command(aliases=["presence"])
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def activity(self, ctx, activity_type: str.lower, *, message: str = ""):
        """
        Set an activity status for the bot.

        Possible activity types:
            - `playing`
            - `streaming`
            - `listening`
            - `watching`

        When activity type is set to `listening`,
        it must be followed by a "to": "listening to..."

        When activity type is set to `streaming`, you can set
        the linked twitch page:
        - `{prefix}config set twitch_url https://www.twitch.tv/somechannel/`

        To remove the current activity status:
        - `{prefix}activity clear`
        """
        if activity_type == "clear":
            self.bot.config["activity_type"] = None
            self.bot.config["activity_message"] = None
            await self.bot.config.update()
            await self.set_presence()
            embed = Embed(title="Activity Removed", color=self.bot.main_color)
            return await ctx.send(embed=embed)

        if not message:
            raise commands.MissingRequiredArgument(param(name="message"))

        activity, msg = (
            await self.set_presence(
                activity_identifier=activity_type,
                activity_by_key=True,
                activity_message=message,
            )
        )["activity"]
        if activity is None:
            raise commands.MissingRequiredArgument(param(name="activity"))

        self.bot.config["activity_type"] = activity.type.value
        self.bot.config["activity_message"] = message
        await self.bot.config.update()

        embed = Embed(
            title="Activity Changed", description=msg, color=self.bot.main_color
        )
        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def status(self, ctx, *, status_type: str.lower):
        """
        Set a status for the bot.

        Possible status types:
            - `online`
            - `idle`
            - `dnd`
            - `do_not_disturb` or `do not disturb`
            - `invisible` or `offline`

        To remove the current status:
        - `{prefix}status clear`
        """
        if status_type == "clear":
            self.bot.config["status"] = None
            await self.bot.config.update()
            await self.set_presence()
            embed = Embed(title="Status Removed", color=self.bot.main_color)
            return await ctx.send(embed=embed)
        status_type = status_type.replace(" ", "_")

        status, msg = (
            await self.set_presence(status_identifier=status_type, status_by_key=True)
        )["status"]
        if status is None:
            raise commands.MissingRequiredArgument(param(name="status"))

        self.bot.config["status"] = status.value
        await self.bot.config.update()

        embed = Embed(
            title="Status Changed", description=msg, color=self.bot.main_color
        )
        return await ctx.send(embed=embed)

    async def set_presence(
        self,
        *,
        status_identifier=None,
        status_by_key=True,
        activity_identifier=None,
        activity_by_key=True,
        activity_message=None,
    ):

        activity = status = None
        if status_identifier is None:
            status_identifier = self.bot.config.get("status", None)
            status_by_key = False

        try:
            if status_by_key:
                status = Status[status_identifier]
            else:
                status = Status(status_identifier)
        except (KeyError, ValueError):
            if status_identifier is not None:
                msg = f"Invalid status type: {status_identifier}"
                logger.warning(error(msg))

        if activity_identifier is None:
            if activity_message is not None:
                raise ValueError(
                    "activity_message must be None " "if activity_identifier is None."
                )
            activity_identifier = self.bot.config.get("activity_type", None)
            activity_by_key = False

        try:
            if activity_by_key:
                activity_type = ActivityType[activity_identifier]
            else:
                activity_type = ActivityType(activity_identifier)
        except (KeyError, ValueError):
            if activity_identifier is not None:
                msg = f"Invalid activity type: {activity_identifier}"
                logger.warning(error(msg))
        else:
            url = None
            activity_message = (
                activity_message or self.bot.config.get("activity_message", "")
            ).strip()

            if activity_type == ActivityType.listening:
                if activity_message.lower().startswith("to "):
                    # The actual message is after listening to [...]
                    # discord automatically add the "to"
                    activity_message = activity_message[3:].strip()
            elif activity_type == ActivityType.streaming:
                url = self.bot.config.get(
                    "twitch_url", "https://www.twitch.tv/discord-modmail/"
                )

            if activity_message:
                activity = Activity(type=activity_type, name=activity_message, url=url)
            else:
                msg = "You must supply an activity message to use custom activity."
                logger.warning(error(msg))

        await self.bot.change_presence(activity=activity, status=status)

        presence = {
            "activity": (None, "No activity has been set."),
            "status": (None, "No status has been set."),
        }
        if activity is not None:
            use_to = "to " if activity.type == ActivityType.listening else ""
            msg = f"Activity set to: {activity.type.name.capitalize()} "
            msg += f"{use_to}{activity.name}."
            presence["activity"] = (activity, msg)
        if status is not None:
            msg = f"Status set to: {status.value}."
            presence["status"] = (status, msg)
        return presence

    @commands.Cog.listener()
    async def on_ready(self):
        # Wait until config cache is populated with stuff from db
        await self.bot.config.wait_until_ready()
        logger.info(info(self.presence["activity"][1]))
        logger.info(info(self.presence["status"][1]))

    async def loop_presence(self):
        """Set presence to the configured value every hour."""
        await self.bot.config.wait_until_ready()
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            self.presence = await self.set_presence()
            await asyncio.sleep(600)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @trigger_typing
    async def ping(self, ctx):
        """Pong! Returns your websocket latency."""
        embed = Embed(
            title="Pong! Websocket Latency:",
            description=f"{self.bot.ws.latency * 1000:.4f} ms",
            color=self.bot.main_color,
        )
        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def mention(self, ctx, *, mention: str = None):
        """
        Change what the bot mentions at the start of each thread.

        Type only `{prefix}mention` to retrieve your current "mention" message.
        """
        current = self.bot.config.get("mention", "@here")

        if mention is None:
            embed = Embed(
                title="Current text",
                color=self.bot.main_color,
                description=str(current),
            )
        else:
            embed = Embed(
                title="Changed mention!",
                description=f"On thread creation the bot now says {mention}.",
                color=self.bot.main_color,
            )
            self.bot.config["mention"] = mention
            await self.bot.config.update()

        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def prefix(self, ctx, *, prefix=None):
        """
        Change the prefix of the bot.

        Type only `{prefix}prefix` to retrieve your current bot prefix.
        """

        current = self.bot.prefix
        embed = Embed(
            title="Current prefix", color=self.bot.main_color, description=f"{current}"
        )

        if prefix is None:
            await ctx.send(embed=embed)
        else:
            embed.title = "Changed prefix!"
            embed.description = f"Set prefix to `{prefix}`"
            self.bot.config["prefix"] = prefix
            await self.bot.config.update()
            await ctx.send(embed=embed)

    @commands.group(aliases=["configuration"], invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config(self, ctx):
        """
        Modify changeable configuration variables for this bot.

        Type `{prefix}config options` to view a list
        of valid configuration variables.

        To set a configuration variable:
        - `{prefix}config set varname value here`

        To remove a configuration variable:
        - `{prefix}config remove varname`
        """
        await ctx.send_help(ctx.command)

    @config.command(name="options", aliases=["list"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config_options(self, ctx):
        """Return a list of valid configuration names you can change."""
        allowed = self.bot.config.allowed_to_change_in_command
        valid = ", ".join(f"`{k}`" for k in allowed)
        embed = Embed(title="Valid Keys", description=valid, color=self.bot.main_color)
        return await ctx.send(embed=embed)

    @config.command(name="set", aliases=["add"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config_set(self, ctx, key: str.lower, *, value: str):
        """Set a configuration variable and its value."""

        keys = self.bot.config.allowed_to_change_in_command

        if key in keys:
            try:
                value, value_text = await self.bot.config.clean_data(key, value)
            except InvalidConfigError as exc:
                embed = exc.embed
            else:
                await self.bot.config.update({key: value})
                embed = Embed(
                    title="Success",
                    color=self.bot.main_color,
                    description=f"Set `{key}` to `{value_text}`",
                )
        else:
            embed = Embed(
                title="Error",
                color=Color.red(),
                description=f"{key} is an invalid key.",
            )
            valid_keys = [f"`{k}`" for k in keys]
            embed.add_field(name="Valid keys", value=", ".join(valid_keys))

        return await ctx.send(embed=embed)

    @config.command(name="remove", aliases=["del", "delete", "rm"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config_remove(self, ctx, key: str.lower):
        """Delete a set configuration variable."""
        keys = self.bot.config.allowed_to_change_in_command
        if key in keys:
            try:
                del self.bot.config.cache[key]
                await self.bot.config.update()
            except KeyError:
                # when no values were set
                pass
            embed = Embed(
                title="Success",
                color=self.bot.main_color,
                description=f"`{key}` had been deleted from the config.",
            )
        else:
            embed = Embed(
                title="Error",
                color=Color.red(),
                description=f"{key} is an invalid key.",
            )
            valid_keys = [f"`{k}`" for k in keys]
            embed.add_field(name="Valid keys", value=", ".join(valid_keys))

        return await ctx.send(embed=embed)

    @config.command(name="get")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config_get(self, ctx, key: str.lower = None):
        """
        Show the configuration variables that are currently set.

        Leave `key` empty to show all currently set configuration variables.
        """
        keys = self.bot.config.allowed_to_change_in_command

        if key:
            if key in keys:
                desc = f"`{key}` is set to `{self.bot.config.get(key)}`"
                embed = Embed(color=self.bot.main_color, description=desc)
                embed.set_author(
                    name="Config variable", icon_url=self.bot.user.avatar_url
                )

            else:
                embed = Embed(
                    title="Error",
                    color=Color.red(),
                    description=f"`{key}` is an invalid key.",
                )
                valid_keys = [f"`{k}`" for k in keys]
                embed.add_field(name="Valid keys", value=", ".join(valid_keys))

        else:
            embed = Embed(
                color=self.bot.main_color,
                description="Here is a list of currently "
                "set configuration variables.",
            )
            embed.set_author(name="Current config", icon_url=self.bot.user.avatar_url)

            config = {
                key: val
                for key, val in self.bot.config.cache.items()
                if val and key in keys
            }

            for name, value in reversed(list(config.items())):
                embed.add_field(name=name, value=f"`{value}`", inline=False)

        return await ctx.send(embed=embed)

    @commands.group(aliases=["aliases"], invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def alias(self, ctx):
        """
        Create shortcuts to bot commands.

        When `{prefix}alias` is used by itself, this will retrieve
        a list of alias that are currently set.

        To use alias:

        First create a snippet using:
        - `{prefix}alias add alias-name other-command`

        For example:
        - `{prefix}alias add r reply`
        - Now you can use `{prefix}r` as an replacement for `{prefix}reply`.

        See also `{prefix}snippets`.
        """

        embeds = []
        desc = "Here is a list of aliases that are currently configured."

        if self.bot.aliases:
            embed = Embed(color=self.bot.main_color, description=desc)
        else:
            embed = Embed(
                color=self.bot.main_color,
                description="You dont have any aliases at the moment.",
            )
        embed.set_author(name="Command aliases", icon_url=ctx.guild.icon_url)
        embed.set_footer(text=f"Do {self.bot.prefix}" "help aliases for more commands.")
        embeds.append(embed)

        for name, value in self.bot.aliases.items():
            if len(embed.fields) == 5:
                embed = Embed(color=self.bot.main_color, description=desc)
                embed.set_author(name="Command aliases", icon_url=ctx.guild.icon_url)
                embed.set_footer(
                    text=f"Do {self.bot.prefix}help " "aliases for more commands."
                )

                embeds.append(embed)
            embed.add_field(name=name, value=value, inline=False)

        session = PaginatorSession(ctx, *embeds)
        return await session.run()

    @alias.command(name="add")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def alias_add(self, ctx, name: str.lower, *, value):
        """Add an alias."""
        if "aliases" not in self.bot.config.cache:
            self.bot.config["aliases"] = {}

        if self.bot.get_command(name) or self.bot.config.aliases.get(name):
            embed = Embed(
                title="Error",
                color=Color.red(),
                description="A command or alias already exists "
                f"with the same name: `{name}`.",
            )
            return await ctx.send(embed=embed)

        if not self.bot.get_command(value.split()[0]):
            embed = Embed(
                title="Error",
                color=Color.red(),
                description="The command you are attempting to point "
                f"to does not exist: `{value.split()[0]}`.",
            )
            return await ctx.send(embed=embed)

        self.bot.config.aliases[name] = value
        await self.bot.config.update()

        embed = Embed(
            title="Added alias",
            color=self.bot.main_color,
            description=f"`{name}` points to: {value}",
        )

        return await ctx.send(embed=embed)

    @alias.command(name="remove", aliases=["del", "delete", "rm"])
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def alias_remove(self, ctx, *, name: str.lower):
        """Remove an alias."""

        if "aliases" not in self.bot.config.cache:
            self.bot.config["aliases"] = {}

        if self.bot.config.aliases.get(name):
            del self.bot.config["aliases"][name]
            await self.bot.config.update()

            embed = Embed(
                title="Removed alias",
                color=self.bot.main_color,
                description=f"`{name}` no longer exists.",
            )

        else:
            embed = Embed(
                title="Error",
                color=Color.red(),
                description=f"Alias `{name}` does not exist.",
            )

        return await ctx.send(embed=embed)

    @commands.group(aliases=["perms"], invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions(self, ctx):
        """
        Set the permissions for Modmail commands.

        You may set permissions based on individual command names, or permission
        levels.

        Acceptable permission levels are:
            - **Owner** [5] (absolute control over the bot)
            - **Administrator** [4] (administrative powers such as setting activities)
            - **Moderator** [3] (ability to block)
            - **Supporter** [2] (access to core Modmail supporting functions)
            - **Regular** [1] (most basic interactions such as help and about)

        By default, owner is set to the absolute bot owner and regular is `@everyone`.

        Note: You will still have to manually give/take permission to the Modmail
        category to users/roles.
        """
        await ctx.send_help(ctx.command)

    @permissions.group(name="add", invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_add(self, ctx):
        """Add a permission to a command or a permission level."""
        await ctx.send_help(ctx.command)

    @permissions_add.command(name="command")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_add_command(
        self, ctx, command: str, *, user_or_role: Union[User, Role, str]
    ):
        """
        Add a user, role, or everyone permission to use a command.

        Do not ping `@everyone` for granting permission to everyone, use "everyone" or "all" instead,
        `user_or_role` may be a role ID, name, mention, user ID, name, mention, "all", or "everyone".
        """
        if command not in self.bot.all_commands:
            embed = Embed(
                title="Error",
                color=Color.red(),
                description="The command you are attempting to point "
                f"to does not exist: `{command}`.",
            )
            return await ctx.send(embed=embed)

        if hasattr(user_or_role, "id"):
            value = user_or_role.id
        elif user_or_role in {"everyone", "all"}:
            value = -1
        else:
            raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

        await self.bot.update_perms(self.bot.all_commands[command].name, value)
        embed = Embed(
            title="Success",
            color=self.bot.main_color,
            description=f"Permission for {command} was successfully updated.",
        )
        return await ctx.send(embed=embed)

    @permissions_add.command(name="level", aliases=["group"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_add_level(
        self, ctx, level: str, *, user_or_role: Union[User, Role, str]
    ):
        """
        Add a user, role, or everyone permission to use commands of a permission level.

        Do not ping `@everyone` for granting permission to everyone, use "everyone" or "all" instead,
        `user_or_role` may be a role ID, name, mention, user ID, name, mention, "all", or "everyone".
        """
        if level.upper() not in PermissionLevel.__members__:
            embed = Embed(
                title="Error",
                color=Color.red(),
                description="The permission level you are attempting to point "
                f"to does not exist: `{level}`.",
            )
            return await ctx.send(embed=embed)

        if hasattr(user_or_role, "id"):
            value = user_or_role.id
        elif user_or_role in {"everyone", "all"}:
            value = -1
        else:
            raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

        await self.bot.update_perms(PermissionLevel[level.upper()], value)
        embed = Embed(
            title="Success",
            color=self.bot.main_color,
            description=f"Permission for {level} was successfully updated.",
        )
        return await ctx.send(embed=embed)

    @permissions.group(
        name="remove",
        aliases=["del", "delete", "rm", "revoke"],
        invoke_without_command=True,
    )
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_remove(self, ctx):
        """Remove permission to use a command or permission level."""
        await ctx.send_help(ctx.command)

    @permissions_remove.command(name="command")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_remove_command(
        self, ctx, command: str, *, user_or_role: Union[User, Role, str]
    ):
        """
        Remove a user, role, or everyone permission to use a command.

        Do not ping `@everyone` for granting permission to everyone, use "everyone" or "all" instead,
        `user_or_role` may be a role ID, name, mention, user ID, name, mention, "all", or "everyone".
        """
        if command not in self.bot.all_commands:
            embed = Embed(
                title="Error",
                color=Color.red(),
                description="The command you are attempting to point "
                f"to does not exist: `{command}`.",
            )
            return await ctx.send(embed=embed)

        if hasattr(user_or_role, "id"):
            value = user_or_role.id
        elif user_or_role in {"everyone", "all"}:
            value = -1
        else:
            raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

        await self.bot.update_perms(
            self.bot.all_commands[command].name, value, add=False
        )
        embed = Embed(
            title="Success",
            color=self.bot.main_color,
            description=f"Permission for {command} was successfully updated.",
        )
        return await ctx.send(embed=embed)

    @permissions_remove.command(name="level", aliases=["group"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_remove_level(
        self, ctx, level: str, *, user_or_role: Union[User, Role, str]
    ):
        """
        Remove a user, role, or everyone permission to use commands of a permission level.

        Do not ping `@everyone` for granting permission to everyone, use "everyone" or "all" instead,
        `user_or_role` may be a role ID, name, mention, user ID, name, mention, "all", or "everyone".
        """
        if level.upper() not in PermissionLevel.__members__:
            embed = Embed(
                title="Error",
                color=Color.red(),
                description="The permission level you are attempting to point "
                f"to does not exist: `{level}`.",
            )
            return await ctx.send(embed=embed)

        if hasattr(user_or_role, "id"):
            value = user_or_role.id
        elif user_or_role in {"everyone", "all"}:
            value = -1
        else:
            raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

        await self.bot.update_perms(PermissionLevel[level.upper()], value, add=False)
        embed = Embed(
            title="Success",
            color=self.bot.main_color,
            description=f"Permission for {level} was successfully updated.",
        )
        return await ctx.send(embed=embed)

    @permissions.group(name="get", invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_get(self, ctx, *, user_or_role: Union[User, Role, str]):
        """
        View the currently-set permissions.

        You can specify `user_or_role` as an alternative to get-by-command or get-by-level.

        Do not ping `@everyone` for granting permission to everyone, use "everyone" or "all" instead,
        `user_or_role` may be a role ID, name, mention, user ID, name, mention, "all", or "everyone".
        """

        if hasattr(user_or_role, "id"):
            value = user_or_role.id
        elif user_or_role in {"everyone", "all"}:
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
        mention = user_or_role.name if hasattr(user_or_role, "name") else user_or_role
        desc_cmd = (
            ", ".join(map(lambda x: f"`{x}`", cmds))
            if cmds
            else "No permission entries found."
        )
        desc_level = (
            ", ".join(map(lambda x: f"`{x}`", levels))
            if levels
            else "No permission entries found."
        )

        embeds = [
            Embed(
                title=f"{mention} has permission with the following commands:",
                description=desc_cmd,
                color=self.bot.main_color,
            ),
            Embed(
                title=f"{mention} has permission with the following permission groups:",
                description=desc_level,
                color=self.bot.main_color,
            ),
        ]
        p_session = PaginatorSession(ctx, *embeds)
        return await p_session.run()

    @permissions_get.command(name="command")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_get_command(self, ctx, *, command: str = None):
        """View currently-set permissions for a command."""

        def get_command(cmd):
            permissions = self.bot.config.command_permissions.get(cmd.name, [])
            if not permissions:
                embed = Embed(
                    title=f"Permission entries for command `{cmd.name}`:",
                    description="No permission entries found.",
                    color=self.bot.main_color,
                )
            else:
                values = []
                for perm in permissions:
                    if perm == -1:
                        values.insert(0, "**everyone**")
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
                    title=f"Permission entries for command `{cmd.name}`:",
                    description=", ".join(values),
                    color=self.bot.main_color,
                )
            return embed

        embeds = []
        if command is not None:
            if command not in self.bot.all_commands:
                embed = Embed(
                    title="Error",
                    color=Color.red(),
                    description="The command you are attempting to point "
                    f"to does not exist: `{command}`.",
                )
                return await ctx.send(embed=embed)
            embeds.append(get_command(self.bot.all_commands[command]))
        else:
            for cmd in self.bot.commands:
                embeds.append(get_command(cmd))

        p_session = PaginatorSession(ctx, *embeds)
        return await p_session.run()

    @permissions_get.command(name="level", aliases=["group"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_get_level(self, ctx, *, level: str = None):
        """View currently-set permissions for commands of a permission level."""

        def get_level(perm_level):
            permissions = self.bot.config.level_permissions.get(perm_level.name, [])
            if not permissions:
                embed = Embed(
                    title="Permission entries for permission "
                    f"level `{perm_level.name}`:",
                    description="No permission entries found.",
                    color=self.bot.main_color,
                )
            else:
                values = []
                for perm in permissions:
                    if perm == -1:
                        values.insert(0, "**everyone**")
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
                    title=f"Permission entries for permission level `{perm_level.name}`:",
                    description=", ".join(values),
                    color=self.bot.main_color,
                )
            return embed

        embeds = []
        if level is not None:
            if level.upper() not in PermissionLevel.__members__:
                embed = Embed(
                    title="Error",
                    color=Color.red(),
                    description="The permission level you are attempting to point "
                    f"to does not exist: `{level}`.",
                )
                return await ctx.send(embed=embed)
            embeds.append(get_level(PermissionLevel[level.upper()]))
        else:
            for perm_level in PermissionLevel:
                embeds.append(get_level(perm_level))

        p_session = PaginatorSession(ctx, *embeds)
        return await p_session.run()

    @commands.group(
        invoke_without_command=True, aliases=["oauth2", "auth", "authentication"]
    )
    @checks.has_permissions(PermissionLevel.OWNER)
    async def oauth(self, ctx):
        """Commands relating to Logviewer oauth2 login authentication.
        
        This functionality on your logviewer site is a [**Patron**](https://patreon.com/kyber) only feature.
        """
        await ctx.send_help(ctx.command)

    @oauth.command(name="whitelist")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def oauth_whitelist(self, ctx, target: Union[User, Role]):
        """
        Whitelist or un-whitelist a user or role to have access to logs.

        `target` may be a role ID, name, mention, user ID, name, or mention.
        """
        whitelisted = self.bot.config["oauth_whitelist"]

        if target.id in whitelisted:
            whitelisted.remove(target.id)
            removed = True
        else:
            whitelisted.append(target.id)
            removed = False

        await self.bot.config.update()

        embed = Embed(color=self.bot.main_color)
        embed.title = "Success"

        if not hasattr(target, "mention"):
            target = self.bot.get_user(target.id) or self.bot.modmail_guild.get_role(
                target.id
            )

        embed.description = (
            f"{'Un-w' if removed else 'W'}hitelisted " f"{target.mention} to view logs."
        )

        await ctx.send(embed=embed)

    @oauth.command(name="show", aliases=["get", "list", "view"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def oauth_show(self, ctx):
        """Shows a list of users and roles that are whitelisted to view logs."""
        whitelisted = self.bot.config["oauth_whitelist"]

        users = []
        roles = []

        for id_ in whitelisted:
            user = self.bot.get_user(id_)
            if user:
                users.append(user)
            role = self.bot.modmail_guild.get_role(id_)
            if role:
                roles.append(role)

        embed = Embed(color=self.bot.main_color)
        embed.title = "Oauth Whitelist"

        embed.add_field(
            name="Users", value=" ".join(u.mention for u in users) or "None"
        )
        embed.add_field(
            name="Roles", value=" ".join(r.mention for r in roles) or "None"
        )

        await ctx.send(embed=embed)

    @commands.command(hidden=True, name="eval")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def eval_(self, ctx, *, body: str):
        """Evaluates Python code."""

        env = {
            "ctx": ctx,
            "bot": self.bot,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "source": inspect.getsource,
            "discord": __import__("discord"),
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
            return list(filter(lambda a: a != "", pages))

        try:
            exec(to_compile, env)  # pylint: disable=exec-used
        except Exception as exc:  # pylint: disable=broad-except
            await ctx.send(f"```py\n{exc.__class__.__name__}: {exc}\n```")
            return await ctx.message.add_reaction("\u2049")

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:  # pylint: disable=broad-except
            value = stdout.getvalue()
            await ctx.send(f"```py\n{value}{traceback.format_exc()}\n```")
            return await ctx.message.add_reaction("\u2049")

        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        await ctx.send(f"```py\n{value}\n```")
                    except Exception:  # pylint: disable=broad-except
                        paginated_text = paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                await ctx.send(f"```py\n{page}\n```")
                                break
                            await ctx.send(f"```py\n{page}\n```")
            else:
                try:
                    await ctx.send(f"```py\n{value}{ret}\n```")
                except Exception:  # pylint: disable=broad-except
                    paginated_text = paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            await ctx.send(f"```py\n{page}\n```")
                            break
                        await ctx.send(f"```py\n{page}\n```")


def setup(bot):
    bot.add_cog(Utility(bot))
