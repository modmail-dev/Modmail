import asyncio
import inspect
import os
import traceback
import random
from contextlib import redirect_stdout
from datetime import datetime
from difflib import get_close_matches
from io import StringIO, BytesIO
from itertools import zip_longest, takewhile
from json import JSONDecodeError, loads
from textwrap import indent
from types import SimpleNamespace
from typing import Union

import discord
from discord.enums import ActivityType, Status
from discord.ext import commands, tasks
from discord.ext.commands.view import StringView

from aiohttp import ClientResponseError
from pkg_resources import parse_version

from core import checks
from core.changelog import Changelog
from core.models import InvalidConfigError, PermissionLevel, getLogger
from core.paginator import EmbedPaginatorSession, MessagePaginatorSession
from core import utils

logger = getLogger(__name__)


class ModmailHelpCommand(commands.HelpCommand):
    async def format_cog_help(self, cog, *, no_cog=False):
        bot = self.context.bot
        prefix = self.clean_prefix

        formats = [""]
        for cmd in await self.filter_commands(
            cog.get_commands() if not no_cog else cog,
            sort=True,
            key=lambda c: (bot.command_perm(c.qualified_name), c.qualified_name),
        ):
            perm_level = bot.command_perm(cmd.qualified_name)
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
            description = (
                cog.description or "No description."
                if not no_cog
                else "Miscellaneous commands without a category."
            )
            embed = discord.Embed(description=f"*{description}*", color=bot.main_color)

            embed.add_field(name="Commands", value=format_ or "No commands.")

            continued = " (Continued)" if embeds else ""
            name = cog.qualified_name + " - Help" if not no_cog else "Miscellaneous Commands"
            embed.set_author(name=name + continued, icon_url=bot.user.avatar_url)

            embed.set_footer(
                text=f'Type "{prefix}{self.command_attrs["name"]} command" '
                "for more info on a specific command."
            )
            embeds.append(embed)
        return embeds

    def process_help_msg(self, help_: str):
        return help_.format(prefix=self.clean_prefix) if help_ else "No help message."

    async def send_bot_help(self, mapping):
        embeds = []
        no_cog_commands = sorted(mapping.pop(None), key=lambda c: c.qualified_name)
        cogs = sorted(mapping, key=lambda c: c.qualified_name)

        bot = self.context.bot

        # always come first
        default_cogs = [bot.get_cog("Modmail"), bot.get_cog("Utility"), bot.get_cog("Plugins")]

        default_cogs.extend(c for c in cogs if c not in default_cogs)

        for cog in default_cogs:
            embeds.extend(await self.format_cog_help(cog))
        if no_cog_commands:
            embeds.extend(await self.format_cog_help(no_cog_commands, no_cog=True))

        session = EmbedPaginatorSession(self.context, *embeds, destination=self.get_destination())
        return await session.run()

    async def send_cog_help(self, cog):
        embeds = await self.format_cog_help(cog)
        session = EmbedPaginatorSession(self.context, *embeds, destination=self.get_destination())
        return await session.run()

    async def _get_help_embed(self, topic):
        if not await self.filter_commands([topic]):
            return
        perm_level = self.context.bot.command_perm(topic.qualified_name)
        if perm_level is not PermissionLevel.INVALID:
            perm_level = f"{perm_level.name} [{perm_level}]"
        else:
            perm_level = "NONE"

        embed = discord.Embed(
            title=f"`{self.get_command_signature(topic)}`",
            color=self.context.bot.main_color,
            description=self.process_help_msg(topic.help),
        )
        return embed, perm_level

    async def send_command_help(self, command):
        topic = await self._get_help_embed(command)
        if topic is not None:
            topic[0].set_footer(text=f"Permission level: {topic[1]}")
            await self.get_destination().send(embed=topic[0])

    async def send_group_help(self, group):
        topic = await self._get_help_embed(group)
        if topic is None:
            return
        embed = topic[0]
        embed.add_field(name="Permission Level", value=topic[1], inline=False)

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

        embed.add_field(name="Sub Command(s)", value=format_[:1024], inline=False)
        embed.set_footer(
            text=f'Type "{self.clean_prefix}{self.command_attrs["name"]} command" '
            "for more info on a command."
        )

        await self.get_destination().send(embed=embed)

    async def send_error_message(self, error):
        command = self.context.kwargs.get("command")
        val = self.context.bot.snippets.get(command)
        if val is not None:
            embed = discord.Embed(
                title=f"{command} is a snippet.", color=self.context.bot.main_color
            )
            embed.add_field(name=f"`{command}` will send:", value=val)
            return await self.get_destination().send(embed=embed)

        val = self.context.bot.aliases.get(command)
        if val is not None:
            values = utils.parse_alias(val)

            if not values:
                embed = discord.Embed(
                    title="Error",
                    color=self.context.bot.error_color,
                    description=f"Alias `{command}` is invalid, this alias will now be deleted."
                    "This alias will now be deleted.",
                )
                embed.add_field(name=f"{command}` used to be:", value=val)
                self.context.bot.aliases.pop(command)
                await self.context.bot.config.update()
            else:
                if len(values) == 1:
                    embed = discord.Embed(
                        title=f"{command} is an alias.", color=self.context.bot.main_color
                    )
                    embed.add_field(name=f"`{command}` points to:", value=values[0])
                else:
                    embed = discord.Embed(
                        title=f"{command} is an alias.",
                        color=self.context.bot.main_color,
                        description=f"**`{command}` points to the following steps:**",
                    )
                    for i, val in enumerate(values, start=1):
                        embed.add_field(name=f"Step {i}:", value=val)

            embed.set_footer(
                text=f'Type "{self.clean_prefix}{self.command_attrs["name"]} alias" '
                "for more details on aliases."
            )
            return await self.get_destination().send(embed=embed)

        logger.warning("CommandNotFound: %s", error)

        embed = discord.Embed(color=self.context.bot.error_color)
        embed.set_footer(text=f'Command/Category "{command}" not found.')

        choices = set()

        for cmd in self.context.bot.walk_commands():
            if not cmd.hidden:
                choices.add(cmd.qualified_name)

        closest = get_close_matches(command, choices)
        if closest:
            embed.add_field(name="Perhaps you meant:", value="\n".join(f"`{x}`" for x in closest))
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
            verify_checks=False,
            command_attrs={
                "help": "Shows this help message.",
                "checks": [checks.has_permissions_predicate(PermissionLevel.REGULAR)],
            },
        )
        self.bot.help_command.cog = self
        self.loop_presence.start()  # pylint: disable=no-member
        if not self.bot.config.get("enable_eval"):
            self.eval_.enabled = False
            logger.info("Eval disabled. enable_eval=False")

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

    @commands.command()
    @checks.has_permissions(PermissionLevel.REGULAR)
    @utils.trigger_typing
    async def changelog(self, ctx, version: str.lower = ""):
        """Shows the changelog of the Modmail."""
        changelog = await Changelog.from_url(self.bot)
        version = version.lstrip("v") if version else changelog.latest_version.version

        try:
            index = [v.version for v in changelog.versions].index(version)
        except ValueError:
            return await ctx.send(
                embed=discord.Embed(
                    color=self.bot.error_color,
                    description=f"The specified version `{version}` could not be found.",
                )
            )

        paginator = EmbedPaginatorSession(ctx, *changelog.embeds)
        try:
            paginator.current = index
            await paginator.run()
        except asyncio.CancelledError:
            pass
        except Exception:
            try:
                await paginator.close()
            finally:
                logger.warning("Failed to display changelog.", exc_info=True)
                await ctx.send(
                    f"View the changelog here: {changelog.latest_version.changelog_url}#v{version[::2]}"
                )

    @commands.command(aliases=["info"])
    @checks.has_permissions(PermissionLevel.REGULAR)
    @utils.trigger_typing
    async def about(self, ctx):
        """Shows information about this bot."""
        embed = discord.Embed(color=self.bot.main_color, timestamp=datetime.utcnow())
        embed.set_author(
            name="Modmail - About",
            icon_url=self.bot.user.avatar_url,
            url="https://discord.gg/F34cRU8",
        )
        embed.set_thumbnail(url=self.bot.user.avatar_url)

        desc = "This is an open source Discord bot that serves as a means for "
        desc += "members to easily communicate with server administrators in "
        desc += "an organised manner."
        embed.description = desc

        embed.add_field(name="Uptime", value=self.bot.uptime)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.2f} ms")
        embed.add_field(name="Version", value=f"`{self.bot.version}`")
        embed.add_field(name="Authors", value="`kyb3r`, `Taki`, `fourjr`")

        changelog = await Changelog.from_url(self.bot)
        latest = changelog.latest_version

        if self.bot.version.is_prerelease:
            stable = next(
                filter(lambda v: not parse_version(v.version).is_prerelease, changelog.versions)
            )
            footer = (
                f"You are on the prerelease version • the latest version is v{stable.version}."
            )
        elif self.bot.version < parse_version(latest.version):
            footer = f"A newer version is available v{latest.version}."
        else:
            footer = "You are up to date with the latest version."

        embed.add_field(
            name="Want Modmail in Your Server?",
            value="Follow the installation guide on [GitHub](https://github.com/kyb3r/modmail/) "
            "and join our [Discord server](https://discord.gg/F34cRU8/)!",
            inline=False,
        )

        embed.add_field(
            name="Support the Developers",
            value="This bot is completely free for everyone. We rely on kind individuals "
            "like you to support us on [`Patreon`](https://patreon.com/kyber) (perks included) "
            "to keep this bot free forever!",
            inline=False,
        )

        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.REGULAR)
    @utils.trigger_typing
    async def sponsors(self, ctx):
        """Shows a list of sponsors."""
        resp = await self.bot.session.get(
            "https://raw.githubusercontent.com/kyb3r/modmail/master/SPONSORS.json"
        )
        data = loads(await resp.text())

        embeds = []

        for elem in data:
            embed = discord.Embed.from_dict(elem["embed"])
            embeds.append(embed)

        random.shuffle(embeds)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    @utils.trigger_typing
    async def debug(self, ctx):
        """Shows the recent application logs of the bot."""

        log_file_name = self.bot.token.split(".")[0]

        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), f"../temp/{log_file_name}.log"
            ),
            "r+",
        ) as f:
            logs = f.read().strip()

        if not logs:
            embed = discord.Embed(
                color=self.bot.main_color,
                title="Debug Logs:",
                description="You don't have any logs at the moment.",
            )
            embed.set_footer(text="Go to Heroku to see your logs.")
            return await ctx.send(embed=embed)

        messages = []

        # Using Haskell formatting because it's similar to Python for exceptions
        # and it does a fine job formatting the logs.
        msg = "```Haskell\n"

        for line in logs.splitlines(keepends=True):
            if msg != "```Haskell\n":
                if len(line) + len(msg) + 3 > 2000:
                    msg += "```"
                    messages.append(msg)
                    msg = "```Haskell\n"
            msg += line
            if len(msg) + 3 > 2000:
                msg = msg[:1993] + "[...]```"
                messages.append(msg)
                msg = "```Haskell\n"

        if msg != "```Haskell\n":
            msg += "```"
            messages.append(msg)

        embed = discord.Embed(color=self.bot.main_color)
        embed.set_footer(text="Debug logs - Navigate using the reactions below.")

        session = MessagePaginatorSession(ctx, *messages, embed=embed)
        session.current = len(messages) - 1
        return await session.run()

    @debug.command(name="hastebin", aliases=["haste"])
    @checks.has_permissions(PermissionLevel.OWNER)
    @utils.trigger_typing
    async def debug_hastebin(self, ctx):
        """Posts application-logs to Hastebin."""

        haste_url = os.environ.get("HASTE_URL", "https://hasteb.in")
        log_file_name = self.bot.token.split(".")[0]

        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), f"../temp/{log_file_name}.log"
            ),
            "rb+",
        ) as f:
            logs = BytesIO(f.read().strip())

        try:
            async with self.bot.session.post(haste_url + "/documents", data=logs) as resp:
                data = await resp.json()
                try:
                    key = data["key"]
                except KeyError:
                    logger.error(data["message"])
                    raise
                embed = discord.Embed(
                    title="Debug Logs",
                    color=self.bot.main_color,
                    description=f"{haste_url}/" + key,
                )
        except (JSONDecodeError, ClientResponseError, IndexError, KeyError):
            embed = discord.Embed(
                title="Debug Logs",
                color=self.bot.main_color,
                description="Something's wrong. We're unable to upload your logs to hastebin.",
            )
            embed.set_footer(text="Go to Heroku to see your logs.")
        await ctx.send(embed=embed)

    @debug.command(name="clear", aliases=["wipe"])
    @checks.has_permissions(PermissionLevel.OWNER)
    @utils.trigger_typing
    async def debug_clear(self, ctx):
        """Clears the locally cached logs."""

        log_file_name = self.bot.token.split(".")[0]

        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), f"../temp/{log_file_name}.log"
            ),
            "w",
        ):
            pass
        await ctx.send(
            embed=discord.Embed(
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
            self.bot.config.remove("activity_type")
            self.bot.config.remove("activity_message")
            await self.bot.config.update()
            await self.set_presence()
            embed = discord.Embed(title="Activity Removed", color=self.bot.main_color)
            return await ctx.send(embed=embed)

        if not message:
            raise commands.MissingRequiredArgument(SimpleNamespace(name="message"))

        try:
            activity_type = ActivityType[activity_type]
        except KeyError:
            raise commands.MissingRequiredArgument(SimpleNamespace(name="activity"))

        activity, _ = await self.set_presence(
            activity_type=activity_type, activity_message=message
        )

        self.bot.config["activity_type"] = activity.type.value
        self.bot.config["activity_message"] = activity.name
        await self.bot.config.update()

        msg = f"Activity set to: {activity.type.name.capitalize()} "
        if activity.type == ActivityType.listening:
            msg += f"to {activity.name}."
        else:
            msg += f"{activity.name}."

        embed = discord.Embed(title="Activity Changed", description=msg, color=self.bot.main_color)
        return await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def status(self, ctx, *, status_type: str.lower):
        """
        Set a status for the bot.

        Possible status types:
            - `online`
            - `idle`
            - `dnd` or `do not disturb`
            - `invisible` or `offline`

        To remove the current status:
        - `{prefix}status clear`
        """
        if status_type == "clear":
            self.bot.config.remove("status")
            await self.bot.config.update()
            await self.set_presence()
            embed = discord.Embed(title="Status Removed", color=self.bot.main_color)
            return await ctx.send(embed=embed)

        status_type = status_type.replace(" ", "_")
        try:
            status = Status[status_type]
        except KeyError:
            raise commands.MissingRequiredArgument(SimpleNamespace(name="status"))

        _, status = await self.set_presence(status=status)

        self.bot.config["status"] = status.value
        await self.bot.config.update()

        msg = f"Status set to: {status.value}."
        embed = discord.Embed(title="Status Changed", description=msg, color=self.bot.main_color)
        return await ctx.send(embed=embed)

    async def set_presence(self, *, status=None, activity_type=None, activity_message=None):

        if status is None:
            status = self.bot.config.get("status")

        if activity_type is None:
            activity_type = self.bot.config.get("activity_type")

        url = None
        activity_message = (activity_message or self.bot.config["activity_message"]).strip()
        if activity_type is not None and not activity_message:
            logger.warning(
                'No activity message found whilst activity is provided, defaults to "Modmail".'
            )
            activity_message = "Modmail"

        if activity_type == ActivityType.listening:
            if activity_message.lower().startswith("to "):
                # The actual message is after listening to [...]
                # discord automatically add the "to"
                activity_message = activity_message[3:].strip()
        elif activity_type == ActivityType.streaming:
            url = self.bot.config["twitch_url"]

        if activity_type is not None:
            activity = discord.Activity(type=activity_type, name=activity_message, url=url)
        else:
            activity = None
        await self.bot.change_presence(activity=activity, status=status)

        return activity, status

    @tasks.loop(minutes=30)
    async def loop_presence(self):
        """Set presence to the configured value every 30 minutes."""
        logger.debug("Resetting presence.")
        await self.set_presence()

    @loop_presence.before_loop
    async def before_loop_presence(self):
        await self.bot.wait_for_connected()
        logger.line()
        activity, status = await self.set_presence()

        if activity is not None:
            msg = f"Activity set to: {activity.type.name.capitalize()} "
            if activity.type == ActivityType.listening:
                msg += f"to {activity.name}."
            else:
                msg += f"{activity.name}."
            logger.info(msg)
        else:
            logger.info("No activity has been set.")
        if status is not None:
            msg = f"Status set to: {status.value}."
            logger.info(msg)
        else:
            logger.info("No status has been set.")

        await asyncio.sleep(1800)
        logger.info("Starting presence loop.")

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @utils.trigger_typing
    async def ping(self, ctx):
        """Pong! Returns your websocket latency."""
        embed = discord.Embed(
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
        # TODO: ability to disable mention.
        current = self.bot.config["mention"]

        if mention is None:
            embed = discord.Embed(
                title="Current mention:", color=self.bot.main_color, description=str(current)
            )
        else:
            embed = discord.Embed(
                title="Changed mention!",
                description=f'On thread creation the bot now says "{mention}".',
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
        embed = discord.Embed(
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

        Type `{prefix}config help config-name` for info
         on a config.

        To set a configuration variable:
        - `{prefix}config set config-name value here`

        To remove a configuration variable:
        - `{prefix}config remove config-name`
        """
        await ctx.send_help(ctx.command)

    @config.command(name="options", aliases=["list"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config_options(self, ctx):
        """Return a list of valid configuration names you can change."""
        embeds = []
        for names in zip_longest(*(iter(sorted(self.bot.config.public_keys)),) * 15):
            description = "\n".join(
                f"`{name}`" for name in takewhile(lambda x: x is not None, names)
            )
            embed = discord.Embed(
                title="Available configuration keys:",
                color=self.bot.main_color,
                description=description,
            )
            embeds.append(embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @config.command(name="set", aliases=["add"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config_set(self, ctx, key: str.lower, *, value: str):
        """Set a configuration variable and its value."""

        keys = self.bot.config.public_keys

        if key in keys:
            try:
                self.bot.config.set(key, value)
                await self.bot.config.update()
                embed = discord.Embed(
                    title="Success",
                    color=self.bot.main_color,
                    description=f"Set `{key}` to `{self.bot.config[key]}`.",
                )
            except InvalidConfigError as exc:
                embed = exc.embed
        else:
            embed = discord.Embed(
                title="Error", color=self.bot.error_color, description=f"{key} is an invalid key."
            )
            valid_keys = [f"`{k}`" for k in sorted(keys)]
            embed.add_field(name="Valid keys", value=", ".join(valid_keys))

        return await ctx.send(embed=embed)

    @config.command(name="remove", aliases=["del", "delete"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config_remove(self, ctx, *, key: str.lower):
        """Delete a set configuration variable."""
        keys = self.bot.config.public_keys
        if key in keys:
            self.bot.config.remove(key)
            await self.bot.config.update()
            embed = discord.Embed(
                title="Success",
                color=self.bot.main_color,
                description=f"`{key}` had been reset to default.",
            )
        else:
            embed = discord.Embed(
                title="Error", color=self.bot.error_color, description=f"{key} is an invalid key."
            )
            valid_keys = [f"`{k}`" for k in sorted(keys)]
            embed.add_field(name="Valid keys", value=", ".join(valid_keys))

        return await ctx.send(embed=embed)

    @config.command(name="get")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config_get(self, ctx, *, key: str.lower = None):
        """
        Show the configuration variables that are currently set.

        Leave `key` empty to show all currently set configuration variables.
        """
        keys = self.bot.config.public_keys

        if key:
            if key in keys:
                desc = f"`{key}` is set to `{self.bot.config[key]}`"
                embed = discord.Embed(color=self.bot.main_color, description=desc)
                embed.set_author(name="Config variable", icon_url=self.bot.user.avatar_url)

            else:
                embed = discord.Embed(
                    title="Error",
                    color=self.bot.error_color,
                    description=f"`{key}` is an invalid key.",
                )
                embed.set_footer(
                    text=f'Type "{self.bot.prefix}config options" for a list of config variables.'
                )

        else:
            embed = discord.Embed(
                color=self.bot.main_color,
                description="Here is a list of currently set configuration variable(s).",
            )
            embed.set_author(name="Current config(s):", icon_url=self.bot.user.avatar_url)
            config = self.bot.config.filter_default(self.bot.config)

            for name, value in config.items():
                if name in self.bot.config.public_keys:
                    embed.add_field(name=name, value=f"`{value}`", inline=False)

        return await ctx.send(embed=embed)

    @config.command(name="help", aliases=["info"])
    @checks.has_permissions(PermissionLevel.OWNER)
    async def config_help(self, ctx, key: str.lower = None):
        """
        Show information on a specified configuration.
        """
        if key is not None and not (
            key in self.bot.config.public_keys or key in self.bot.config.protected_keys
        ):
            closest = get_close_matches(
                key, {**self.bot.config.public_keys, **self.bot.config.protected_keys}
            )
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"`{key}` is an invalid key.",
            )
            if closest:
                embed.add_field(
                    name=f"Perhaps you meant:", value="\n".join(f"`{x}`" for x in closest)
                )
            return await ctx.send(embed=embed)

        config_help = self.bot.config.config_help

        if key is not None and key not in config_help:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"No help details found for `{key}`.",
            )
            return await ctx.send(embed=embed)

        def fmt(val):
            return val.format(prefix=self.bot.prefix, bot=self.bot)

        index = 0
        embeds = []
        for i, (current_key, info) in enumerate(config_help.items()):
            if current_key == key:
                index = i
            embed = discord.Embed(
                title=f"Configuration description on {current_key}:", color=self.bot.main_color
            )
            embed.add_field(name="Default:", value=fmt(info["default"]), inline=False)
            embed.add_field(name="Information:", value=fmt(info["description"]), inline=False)
            if info["examples"]:
                example_text = ""
                for example in info["examples"]:
                    example_text += f"- {fmt(example)}\n"
                embed.add_field(name="Example(s):", value=example_text, inline=False)

            note_text = ""
            for note in info["notes"]:
                note_text += f"- {fmt(note)}\n"
            if note_text:
                embed.add_field(name="Note(s):", value=note_text, inline=False)

            if info.get("image") is not None:
                embed.set_image(url=fmt(info["image"]))

            if info.get("thumbnail") is not None:
                embed.set_thumbnail(url=fmt(info["thumbnail"]))
            embeds += [embed]

        paginator = EmbedPaginatorSession(ctx, *embeds)
        paginator.current = index
        await paginator.run()

    @commands.group(aliases=["aliases"], invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def alias(self, ctx, *, name: str.lower = None):
        """
        Create shortcuts to bot commands.

        When `{prefix}alias` is used by itself, this will retrieve
        a list of alias that are currently set. `{prefix}alias-name` will show what the
        alias point to.

        To use alias:

        First create an alias using:
        - `{prefix}alias add alias-name other-command`

        For example:
        - `{prefix}alias add r reply`
        - Now you can use `{prefix}r` as an replacement for `{prefix}reply`.

        See also `{prefix}snippet`.
        """

        if name is not None:
            val = self.bot.aliases.get(name)
            if val is None:
                embed = utils.create_not_found_embed(name, self.bot.aliases.keys(), "Alias")
                return await ctx.send(embed=embed)

            values = utils.parse_alias(val)

            if not values:
                embed = discord.Embed(
                    title="Error",
                    color=self.bot.error_color,
                    description=f"Alias `{name}` is invalid, this alias will now be deleted."
                    "This alias will now be deleted.",
                )
                embed.add_field(name=f"{name}` used to be:", value=utils.truncate(val, 1024))
                self.bot.aliases.pop(name)
                await self.bot.config.update()
                return await ctx.send(embed=embed)

            if len(values) == 1:
                embed = discord.Embed(
                    title=f'Alias - "{name}":', description=values[0], color=self.bot.main_color
                )
                return await ctx.send(embed=embed)

            else:
                embeds = []
                for i, val in enumerate(values, start=1):
                    embed = discord.Embed(
                        color=self.bot.main_color,
                        title=f'Alias - "{name}" - Step {i}:',
                        description=val,
                    )
                    embeds += [embed]
                session = EmbedPaginatorSession(ctx, *embeds)
                return await session.run()

        if not self.bot.aliases:
            embed = discord.Embed(
                color=self.bot.error_color, description="You dont have any aliases at the moment."
            )
            embed.set_footer(text=f'Do "{self.bot.prefix}help alias" for more commands.')
            embed.set_author(name="Aliases", icon_url=ctx.guild.icon_url)
            return await ctx.send(embed=embed)

        embeds = []

        for i, names in enumerate(zip_longest(*(iter(sorted(self.bot.aliases)),) * 15)):
            description = utils.format_description(i, names)
            embed = discord.Embed(color=self.bot.main_color, description=description)
            embed.set_author(name="Command Aliases", icon_url=ctx.guild.icon_url)
            embeds.append(embed)

        session = EmbedPaginatorSession(ctx, *embeds)
        await session.run()

    @alias.command(name="raw")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def alias_raw(self, ctx, *, name: str.lower):
        """
        View the raw content of an alias.
        """
        val = self.bot.aliases.get(name)
        if val is None:
            embed = utils.create_not_found_embed(name, self.bot.aliases.keys(), "Alias")
            return await ctx.send(embed=embed)

        val = utils.truncate(utils.escape_code_block(val), 2048 - 7)
        embed = discord.Embed(
            title=f'Raw alias - "{name}":', description=f"```\n{val}```", color=self.bot.main_color
        )

        return await ctx.send(embed=embed)

    async def make_alias(self, name, value, action):
        values = utils.parse_alias(value)
        if not values:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description="Invalid multi-step alias, try wrapping each steps in quotes.",
            )
            embed.set_footer(text=f'See "{self.bot.prefix}alias add" for more details.')
            return embed

        if len(values) > 25:
            embed = discord.Embed(
                title="Error", description="Too many steps, max=25.", color=self.bot.error_color
            )
            return embed

        save_aliases = []

        multiple_alias = len(values) > 1

        embed = discord.Embed(title=f"{action} alias", color=self.bot.main_color)

        if not multiple_alias:
            embed.add_field(name=f"`{name}` points to:", value=utils.truncate(values[0], 1024))
        else:
            embed.description = f"`{name}` now points to the following steps:"

        for i, val in enumerate(values, start=1):
            view = StringView(val)
            linked_command = view.get_word().lower()
            message = view.read_rest()

            if not self.bot.get_command(linked_command):
                alias_command = self.bot.aliases.get(linked_command)
                if alias_command is not None:
                    save_aliases.extend(utils.normalize_alias(alias_command, message))
                else:
                    embed = discord.Embed(title="Error", color=self.bot.error_color)

                    if multiple_alias:
                        embed.description = (
                            "The command you are attempting to point "
                            f"to does not exist: `{linked_command}`."
                        )
                    else:
                        embed.description = (
                            "The command you are attempting to point "
                            f"to on step {i} does not exist: `{linked_command}`."
                        )

                    return embed
            else:
                save_aliases.append(val)
            if multiple_alias:
                embed.add_field(name=f"Step {i}:", value=utils.truncate(val, 1024))

        self.bot.aliases[name] = " && ".join(f'"{a}"' for a in save_aliases)
        await self.bot.config.update()
        return embed

    @alias.command(name="add")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def alias_add(self, ctx, name: str.lower, *, value):
        """
        Add an alias.

        Alias also supports multi-step aliases, to create a multi-step alias use quotes
        to wrap each step and separate each step with `&&`. For example:

        - `{prefix}alias add movenreply "move admin-category" && "reply Thanks for reaching out to the admins"`

        However, if you run into problems, try wrapping the command with quotes. For example:

        - This will fail: `{prefix}alias add reply You'll need to type && to work`
        - Correct method: `{prefix}alias add reply "You'll need to type && to work"`
        """
        embed = None
        if self.bot.get_command(name):
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"A command with the same name already exists: `{name}`.",
            )

        elif name in self.bot.aliases:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"Another alias with the same name already exists: `{name}`.",
            )

        elif name in self.bot.snippets:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"A snippet with the same name already exists: `{name}`.",
            )

        elif len(name) > 120:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description="Alias names cannot be longer than 120 characters.",
            )

        if embed is None:
            embed = await self.make_alias(name, value, "Added")
        return await ctx.send(embed=embed)

    @alias.command(name="remove", aliases=["del", "delete"])
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def alias_remove(self, ctx, *, name: str.lower):
        """Remove an alias."""

        if name in self.bot.aliases:
            self.bot.aliases.pop(name)
            await self.bot.config.update()

            embed = discord.Embed(
                title="Removed alias",
                color=self.bot.main_color,
                description=f"Successfully deleted `{name}`.",
            )
        else:
            embed = utils.create_not_found_embed(name, self.bot.aliases.keys(), "Alias")

        return await ctx.send(embed=embed)

    @alias.command(name="edit")
    @checks.has_permissions(PermissionLevel.MODERATOR)
    async def alias_edit(self, ctx, name: str.lower, *, value):
        """
        Edit an alias.
        """
        if name not in self.bot.aliases:
            embed = utils.create_not_found_embed(name, self.bot.aliases.keys(), "Alias")
            return await ctx.send(embed=embed)

        embed = await self.make_alias(name, value, "Edited")
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

        To set permissions, see `{prefix}help permissions add`; and to change permission level for specific
        commands see `{prefix}help permissions override`.

        Note: You will still have to manually give/take permission to the Modmail
        category to users/roles.
        """
        await ctx.send_help(ctx.command)

    @staticmethod
    def _verify_user_or_role(user_or_role):
        if isinstance(user_or_role, discord.Role):
            if user_or_role.is_default():
                return -1
        elif user_or_role in {"everyone", "all"}:
            return -1
        if hasattr(user_or_role, "id"):
            return user_or_role.id
        raise commands.BadArgument(f'User or Role "{user_or_role}" not found')

    @staticmethod
    def _parse_level(name):
        name = name.upper()
        try:
            return PermissionLevel[name]
        except KeyError:
            pass
        transform = {
            "1": PermissionLevel.REGULAR,
            "2": PermissionLevel.SUPPORTER,
            "3": PermissionLevel.MODERATOR,
            "4": PermissionLevel.ADMINISTRATOR,
            "5": PermissionLevel.OWNER,
        }
        return transform.get(name, PermissionLevel.INVALID)

    @permissions.command(name="override")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_override(self, ctx, command_name: str.lower, *, level_name: str):
        """
        Change a permission level for a specific command.

        Examples:
        - `{prefix}perms override reply administrator`
        - `{prefix}perms override "plugin enabled" moderator`

        To undo a permission override, see `{prefix}help permissions remove`.

        Example:
        - `{prefix}perms remove override reply`
        - `{prefix}perms remove override plugin enabled`

        You can retrieve a single or all command level override(s), see`{prefix}help permissions get`.
        """

        command = self.bot.get_command(command_name)
        if command is None:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"The referenced command does not exist: `{command_name}`.",
            )
            return await ctx.send(embed=embed)

        level = self._parse_level(level_name)
        if level is PermissionLevel.INVALID:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"The referenced level does not exist: `{level_name}`.",
            )
        else:
            logger.info(
                "Updated command permission level for `%s` to `%s`.",
                command.qualified_name,
                level.name,
            )
            self.bot.config["override_command_level"][command.qualified_name] = level.name

            await self.bot.config.update()
            embed = discord.Embed(
                title="Success",
                color=self.bot.main_color,
                description="Successfully set command permission level for "
                f"`{command.qualified_name}` to `{level.name}`.",
            )
        return await ctx.send(embed=embed)

    @permissions.command(name="add", usage="[command/level] [name] [user/role]")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_add(
        self,
        ctx,
        type_: str.lower,
        name: str,
        *,
        user_or_role: Union[discord.Role, utils.User, str],
    ):
        """
        Add a permission to a command or a permission level.

        For sub commands, wrap the complete command name with quotes.
        To find a list of permission levels, see `{prefix}help perms`.

        Examples:
        - `{prefix}perms add level REGULAR everyone`
        - `{prefix}perms add command reply @user`
        - `{prefix}perms add command "plugin enabled" @role`
        - `{prefix}perms add command help 984301093849028`

        Do not ping `@everyone` for granting permission to everyone, use "everyone" or "all" instead.
        """

        if type_ not in {"command", "level"}:
            return await ctx.send_help(ctx.command)

        command = level = None
        if type_ == "command":
            name = name.lower()
            command = self.bot.get_command(name)
            check = command is not None
        else:
            level = self._parse_level(name)
            check = level is not PermissionLevel.INVALID

        if not check:
            embed = discord.Embed(
                title="Error",
                color=self.bot.error_color,
                description=f"The referenced {type_} does not exist: `{name}`.",
            )
            return await ctx.send(embed=embed)

        value = self._verify_user_or_role(user_or_role)
        if type_ == "command":
            name = command.qualified_name
            await self.bot.update_perms(name, value)
        else:
            await self.bot.update_perms(level, value)
            name = level.name
            if level > PermissionLevel.REGULAR:
                if value == -1:
                    key = self.bot.modmail_guild.default_role
                elif isinstance(user_or_role, discord.Role):
                    key = user_or_role
                else:
                    key = self.bot.modmail_guild.get_member(value)
                if key is not None:
                    logger.info("Granting %s access to Modmail category.", key.name)
                    await self.bot.main_category.set_permissions(key, read_messages=True)

        embed = discord.Embed(
            title="Success",
            color=self.bot.main_color,
            description=f"Permission for `{name}` was successfully updated.",
        )
        return await ctx.send(embed=embed)

    @permissions.command(
        name="remove",
        aliases=["del", "delete", "revoke"],
        usage="[command/level] [name] [user/role] or [override] [command name]",
    )
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_remove(
        self,
        ctx,
        type_: str.lower,
        name: str,
        *,
        user_or_role: Union[discord.Role, utils.User, str] = None,
    ):
        """
        Remove permission to use a command, permission level, or command level override.

        For sub commands, wrap the complete command name with quotes.
        To find a list of permission levels, see `{prefix}help perms`.

        Examples:
        - `{prefix}perms remove level REGULAR everyone`
        - `{prefix}perms remove command reply @user`
        - `{prefix}perms remove command "plugin enabled" @role`
        - `{prefix}perms remove command help 984301093849028`
        - `{prefix}perms remove override block`
        - `{prefix}perms remove override "snippet add"`

        Do not ping `@everyone` for granting permission to everyone, use "everyone" or "all" instead.
        """
        if type_ not in {"command", "level", "override"} or (
            type_ != "override" and user_or_role is None
        ):
            return await ctx.send_help(ctx.command)

        if type_ == "override":
            extension = ctx.kwargs["user_or_role"]
            if extension is not None:
                name += f" {extension}"
            name = name.lower()
            name = getattr(self.bot.get_command(name), "qualified_name", name)
            level = self.bot.config["override_command_level"].get(name)
            if level is None:
                perm = self.bot.command_perm(name)
                embed = discord.Embed(
                    title="Error",
                    color=self.bot.error_color,
                    description=f"The command permission level was never overridden: `{name}`, "
                    f"current permission level is {perm.name}.",
                )
            else:
                logger.info("Restored command permission level for `%s`.", name)
                self.bot.config["override_command_level"].pop(name)
                await self.bot.config.update()
                perm = self.bot.command_perm(name)
                embed = discord.Embed(
                    title="Success",
                    color=self.bot.main_color,
                    description=f"Command permission level for `{name}` was successfully restored to {perm.name}.",
                )
            return await ctx.send(embed=embed)

        level = None
        if type_ == "command":
            name = name.lower()
            name = getattr(self.bot.get_command(name), "qualified_name", name)
        else:
            level = self._parse_level(name)
            if level is PermissionLevel.INVALID:
                embed = discord.Embed(
                    title="Error",
                    color=self.bot.error_color,
                    description=f"The referenced level does not exist: `{name}`.",
                )
                return await ctx.send(embed=embed)
            name = level.name

        value = self._verify_user_or_role(user_or_role)
        await self.bot.update_perms(level or name, value, add=False)

        if type_ == "level":
            if level > PermissionLevel.REGULAR:
                if value == -1:
                    logger.info("Denying @everyone access to Modmail category.")
                    await self.bot.main_category.set_permissions(
                        self.bot.modmail_guild.default_role, read_messages=False
                    )
                elif isinstance(user_or_role, discord.Role):
                    logger.info("Denying %s access to Modmail category.", user_or_role.name)
                    await self.bot.main_category.set_permissions(user_or_role, overwrite=None)
                else:
                    member = self.bot.modmail_guild.get_member(value)
                    if member is not None and member != self.bot.modmail_guild.me:
                        logger.info("Denying %s access to Modmail category.", member.name)
                        await self.bot.main_category.set_permissions(member, overwrite=None)

        embed = discord.Embed(
            title="Success",
            color=self.bot.main_color,
            description=f"Permission for `{name}` was successfully updated.",
        )
        return await ctx.send(embed=embed)

    def _get_perm(self, ctx, name, type_):
        if type_ == "command":
            permissions = self.bot.config["command_permissions"].get(name, [])
        else:
            permissions = self.bot.config["level_permissions"].get(name, [])
        if not permissions:
            embed = discord.Embed(
                title=f"Permission entries for {type_} `{name}`:",
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

            embed = discord.Embed(
                title=f"Permission entries for {type_} `{name}`:",
                description=", ".join(values),
                color=self.bot.main_color,
            )
        return embed

    @permissions.command(name="get", usage="[@user] or [command/level/override] [name]")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def permissions_get(
        self, ctx, user_or_role: Union[discord.Role, utils.User, str], *, name: str = None
    ):
        """
        View the currently-set permissions.

        To find a list of permission levels, see `{prefix}help perms`.

        To view all command and level permissions:

        Examples:
        - `{prefix}perms get @user`
        - `{prefix}perms get 984301093849028`

        To view all users and roles of a command or level permission:

        Examples:
        - `{prefix}perms get command reply`
        - `{prefix}perms get command plugin remove`
        - `{prefix}perms get level SUPPORTER`

        To view command level overrides:

        Examples:
        - `{prefix}perms get override block`
        - `{prefix}perms get override permissions add`

        Do not ping `@everyone` for granting permission to everyone, use "everyone" or "all" instead.
        """

        if name is None and user_or_role not in {"command", "level", "override"}:
            value = self._verify_user_or_role(user_or_role)

            cmds = []
            levels = []

            done = set()
            for command in self.bot.walk_commands():
                if command not in done:
                    done.add(command)
                    permissions = self.bot.config["command_permissions"].get(
                        command.qualified_name, []
                    )
                    if value in permissions:
                        cmds.append(command.qualified_name)

            for level in PermissionLevel:
                permissions = self.bot.config["level_permissions"].get(level.name, [])
                if value in permissions:
                    levels.append(level.name)

            mention = getattr(user_or_role, "name", getattr(user_or_role, "id", user_or_role))
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
                discord.Embed(
                    title=f"{mention} has permission with the following commands:",
                    description=desc_cmd,
                    color=self.bot.main_color,
                ),
                discord.Embed(
                    title=f"{mention} has permission with the following permission levels:",
                    description=desc_level,
                    color=self.bot.main_color,
                ),
            ]
        else:
            user_or_role = (user_or_role or "").lower()
            if user_or_role == "override":
                if name is None:
                    done = set()

                    overrides = {}
                    for command in self.bot.walk_commands():
                        if command not in done:
                            done.add(command)
                            level = self.bot.config["override_command_level"].get(
                                command.qualified_name
                            )
                            if level is not None:
                                overrides[command.qualified_name] = level

                    embeds = []
                    if not overrides:
                        embeds.append(
                            discord.Embed(
                                title="Permission Overrides",
                                description="You don't have any command level overrides at the moment.",
                                color=self.bot.error_color,
                            )
                        )
                    else:
                        for items in zip_longest(*(iter(sorted(overrides.items())),) * 15):
                            description = "\n".join(
                                ": ".join((f"`{name}`", level))
                                for name, level in takewhile(lambda x: x is not None, items)
                            )
                            embed = discord.Embed(
                                color=self.bot.main_color, description=description
                            )
                            embed.set_author(
                                name="Permission Overrides", icon_url=ctx.guild.icon_url
                            )
                            embeds.append(embed)

                    session = EmbedPaginatorSession(ctx, *embeds)
                    return await session.run()

                name = name.lower()
                name = getattr(self.bot.get_command(name), "qualified_name", name)
                level = self.bot.config["override_command_level"].get(name)
                perm = self.bot.command_perm(name)
                if level is None:
                    embed = discord.Embed(
                        title="Error",
                        color=self.bot.error_color,
                        description=f"The command permission level was never overridden: `{name}`, "
                        f"current permission level is {perm.name}.",
                    )
                else:
                    embed = discord.Embed(
                        title="Success",
                        color=self.bot.main_color,
                        description=f'Permission override for command "{name}" is "{perm.name}".',
                    )

                return await ctx.send(embed=embed)

            if user_or_role not in {"command", "level"}:
                return await ctx.send_help(ctx.command)
            embeds = []
            if name is not None:
                name = name.strip('"')
                command = level = None
                if user_or_role == "command":
                    name = name.lower()
                    command = self.bot.get_command(name)
                    check = command is not None
                else:
                    level = self._parse_level(name)
                    check = level is not PermissionLevel.INVALID

                if not check:
                    embed = discord.Embed(
                        title="Error",
                        color=self.bot.error_color,
                        description=f"The referenced {user_or_role} does not exist: `{name}`.",
                    )
                    return await ctx.send(embed=embed)

                if user_or_role == "command":
                    embeds.append(self._get_perm(ctx, command.qualified_name, "command"))
                else:
                    embeds.append(self._get_perm(ctx, level.name, "level"))
            else:
                if user_or_role == "command":
                    done = set()
                    for command in self.bot.walk_commands():
                        if command not in done:
                            done.add(command)
                            embeds.append(self._get_perm(ctx, command.qualified_name, "command"))
                else:
                    for perm_level in PermissionLevel:
                        embeds.append(self._get_perm(ctx, perm_level.name, "level"))

        session = EmbedPaginatorSession(ctx, *embeds)
        return await session.run()

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def oauth(self, ctx):
        """
        Commands relating to logviewer oauth2 login authentication.

        This functionality on your logviewer site is a [**Patron**](https://patreon.com/kyber) only feature.
        """
        await ctx.send_help(ctx.command)

    @oauth.command(name="whitelist")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def oauth_whitelist(self, ctx, target: Union[discord.Role, utils.User]):
        """
        Whitelist or un-whitelist a user or role to have access to logs.

        `target` may be a role ID, name, mention, user ID, name, or mention.
        """
        whitelisted = self.bot.config["oauth_whitelist"]

        # target.id is not int??
        if target.id in whitelisted:
            whitelisted.remove(target.id)
            removed = True
        else:
            whitelisted.append(target.id)
            removed = False

        await self.bot.config.update()

        embed = discord.Embed(color=self.bot.main_color)
        embed.title = "Success"

        if not hasattr(target, "mention"):
            target = self.bot.get_user(target.id) or self.bot.modmail_guild.get_role(target.id)

        embed.description = (
            f"{'Un-w' if removed else 'W'}hitelisted {target.mention} to view logs."
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

        embed = discord.Embed(color=self.bot.main_color)
        embed.title = "Oauth Whitelist"

        embed.add_field(name="Users", value=" ".join(u.mention for u in users) or "None")
        embed.add_field(name="Roles", value=" ".join(r.mention for r in roles) or "None")

        await ctx.send(embed=embed)

    @commands.command(hidden=True, name="eval")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def eval_(self, ctx, *, body: str):
        """Evaluates Python code."""

        logger.warning("Running eval command:\n%s", body)

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

        body = utils.cleanup_code(body)
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
        except Exception as exc:
            await ctx.send(f"```py\n{exc.__class__.__name__}: {exc}\n```")
            return await self.bot.add_reaction(ctx.message, "\u2049")

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            await ctx.send(f"```py\n{value}{traceback.format_exc()}\n```")
            return await self.bot.add_reaction(ctx.message, "\u2049")

        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        await ctx.send(f"```py\n{value}\n```")
                    except Exception:
                        paginated_text = paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                await ctx.send(f"```py\n{page}\n```")
                                break
                            await ctx.send(f"```py\n{page}\n```")
            else:
                try:
                    await ctx.send(f"```py\n{value}{ret}\n```")
                except Exception:
                    paginated_text = paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            await ctx.send(f"```py\n{page}\n```")
                            break
                        await ctx.send(f"```py\n{page}\n```")


def setup(bot):
    bot.add_cog(Utility(bot))
