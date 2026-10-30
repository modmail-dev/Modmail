"""Live suggestions for the string options exposed by the slash adapter."""

import inspect
import re
import typing
from types import SimpleNamespace

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import check_permissions
from core.models import PermissionLevel, getLogger
from core.utils import User

logger = getLogger(__name__)


class SlashAutocomplete:
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _converters(converter):
        if isinstance(converter, commands.Greedy):
            converter = converter.converter
        arguments = typing.get_args(converter)
        if typing.get_origin(converter) is typing.Union:
            return tuple(t for argument in arguments for t in SlashAutocomplete._converters(argument))
        return (converter,)

    @classmethod
    def _entity_types(cls, parameter):
        types = set()
        for converter in cls._converters(parameter.converter):
            if not inspect.isclass(converter):
                continue
            for entity, bases in (
                ("users", (discord.User, commands.UserConverter, User)),
                ("members", (discord.Member, commands.MemberConverter)),
                ("roles", (discord.Role, commands.RoleConverter)),
                ("categories", (discord.CategoryChannel, commands.CategoryChannelConverter)),
                ("channels", (discord.TextChannel, commands.TextChannelConverter)),
            ):
                if issubclass(converter, bases):
                    types.add(entity)
        return types

    def _source(self, command, parameter):
        path, name = command.qualified_name, parameter.name
        group, _, action = path.partition(" ")
        if group in {"snippet", "alias", "args"}:
            if name == "name" and action in {"", "raw", "remove", "edit", "rename"}:
                return {"snippet": "snippets", "alias": "aliases", "args": "args"}[group]
            if group == "alias" and name == "value" and action in {"add", "edit"}:
                return "command_text"
        if group == "config":
            if name == "key" and action in {"set", "get", "remove", "help"}:
                return "config_keys"
            if name == "value" and action == "set":
                return "config_values"
        if path == "help" and name == "command":
            return "help"
        if group == "permissions":
            if name == "command_name" and action == "override":
                return "commands"
            if name == "name" and action in {"add", "remove", "get"}:
                return "permission_names"
        if group == "autotrigger":
            if name == "keyword" and action in {"edit", "remove"}:
                return "auto_triggers"
            if name == "command" and action in {"add", "edit"}:
                return "command_text"
        if group == "plugins" and name == "plugin_name":
            if action in {"add", "registry"}:
                return "registry_plugins"
            if action in {"remove", "update"}:
                return "installed_plugins"
        if path in {"threadmenu option show", "threadmenu option edit", "threadmenu option remove"}:
            return "menu_options" if name == "label" else None
        if path in {"threadmenu submenu show", "threadmenu submenu delete"} and name == "label":
            return "submenus"
        if path.startswith("threadmenu submenu option ") and name == "submenu":
            return "submenus"
        if path == "move" and name == "arguments":
            return "categories"
        if path == "unsnooze" and name == "user":
            return "snoozed_users"
        if self._entity_types(parameter):
            return "entities"
        return None

    def callback(self, command, parameter=None, *, raw_arguments=False):
        if raw_arguments:
            source = {"snippet": "snippets", "alias": "aliases"}.get(command.qualified_name)
        else:
            source = self._source(command, parameter)
        if source is None:
            return None

        async def autocomplete(interaction: discord.Interaction, current: str):
            # Autocomplete does not run command checks. Check access before
            # exposing saved names, configuration, or installed plugins.
            if interaction.guild_id is None or interaction.guild_id != self.bot.inbox_guild_id:
                return []
            ctx = SimpleNamespace(
                bot=self.bot, author=interaction.user, channel=interaction.channel, guild=interaction.guild
            )
            try:
                if not await check_permissions(ctx, command.qualified_name):
                    return []
                prefix = ""
                if parameter is not None and (
                    isinstance(parameter.converter, commands.Greedy)
                    or parameter.kind == inspect.Parameter.VAR_POSITIONAL
                ):
                    # Selected entities are IDs. Preserve them when completing
                    # the next member/role in a multi-value option.
                    head, separator, tail = current.rpartition(" ")
                    if separator and re.fullmatch(
                        r"(?:(?:\d{15,20}|<@!?\d+>|<@&\d+>|silent|silently)\s*)+", head
                    ):
                        prefix, current = head + separator, tail
                return self._choices(self._values(source, command, parameter, interaction), current, prefix)
            except Exception:
                logger.exception("Failed to autocomplete %s.", command.qualified_name)
                return []

        return autocomplete

    @staticmethod
    def _choices(values, current, prefix=""):
        query = current.casefold()
        matches = {}
        for name, value in values:
            name, value = str(name), str(value)
            if not name or not value or len(prefix + value) > 100:
                continue
            if query not in name.casefold() and query not in value.casefold():
                continue
            matches.setdefault(prefix + value, name)
        ordered = sorted(
            matches.items(),
            key=lambda item: (not item[1].casefold().startswith(query), item[1].casefold(), item[0]),
        )
        return [app_commands.Choice(name=name[:100], value=value) for value, name in ordered[:25]]

    def _commands(self):
        for command in self.bot.walk_commands():
            if all(not c.hidden and c.enabled for c in (command, *command.parents)):
                yield command.qualified_name, command.qualified_name

    def _values(self, source, command, parameter, interaction):
        config = self.bot.config
        if source in {"snippets", "aliases", "args", "auto_triggers"}:
            return ((name, name) for name in getattr(self.bot, source))
        if source == "config_keys":
            keys = set(config.public_keys)
            if command.qualified_name == "config help":
                keys.update(config.protected_keys)
            return ((key, key) for key in keys)
        if source == "config_values":
            key = (getattr(interaction.namespace, "key", None) or "").lower()
            if key not in config.public_keys:
                return []
            if key in config.booleans:
                return [("Yes", "yes"), ("No", "no")]
            if key == "snooze_behavior":
                return [("Delete channel", "delete"), ("Move channel", "move")]
            if key.endswith("category_id"):
                return ((category.name, category.id) for category in interaction.guild.categories)
            if key.endswith("channel_id") or key == "unsnooze_notify_channel":
                values = [
                    (f"#{channel.name}", channel.id)
                    for channel in interaction.guild.text_channels
                    if channel.permissions_for(interaction.user).view_channel
                ]
                if key == "unsnooze_notify_channel":
                    values.append(("Current thread", "thread"))
                return values
            return []
        if source in {"commands", "command_text", "help"}:
            values = list(self._commands())
            if source == "commands" and command.qualified_name == "permissions override":
                values.append(("Bulk override", "bulk"))
            elif source == "command_text":
                values.extend((name, name) for name in self.bot.aliases)
            elif source == "help":
                values = [
                    (c.qualified_name, c.qualified_name)
                    for c in self.bot.tree.walk_commands(guild=discord.Object(id=interaction.guild_id))
                    if c.extras.get("modmail_legacy_command")
                ]
                values.extend((name, name) for name in self.bot.cogs)
                values.append(("All commands", "all"))
            return values
        if source == "permission_names":
            namespace = interaction.namespace
            type_ = (
                getattr(namespace, "target" if command.qualified_name == "permissions get" else "type", "")
                or ""
            )
            if type_.lower() == "level":
                return [
                    (level.name.title(), level.name.lower()) for level in PermissionLevel if level.value > 0
                ]
            if type_.lower() in {"command", "override"}:
                return self._commands()
            return []
        if source == "registry_plugins":
            cog = self.bot.get_cog("Plugins")
            return ((name, name) for name in cog.registry) if cog else []
        if source == "installed_plugins":
            return ((name, name) for name in config["plugins"])
        if source == "menu_options":
            return (
                (option.get("label", key), key)
                for key, option in config["thread_creation_menu_options"].items()
            )
        if source == "submenus":
            return ((key.replace("_", " "), key) for key in config["thread_creation_menu_submenus"])
        if source == "snoozed_users":
            return (
                (str(thread.recipient or thread.id), thread.id)
                for thread in self.bot.threads.cache.values()
                if thread.snoozed
            )
        if source == "categories":
            return ((category.name, category.id) for category in interaction.guild.categories)
        if source == "entities":
            values = list(self._entities(parameter, interaction))
            if command.qualified_name == "permissions get" and parameter.name == "user_or_role":
                values.extend((name.title(), name) for name in ("command", "level", "override"))
            if command.qualified_name in {"notify", "unnotify", "subscribe", "unsubscribe"}:
                values.extend((f"@{name}", name) for name in ("everyone", "here"))
            return values
        return []

    def _entities(self, parameter, interaction):
        types = self._entity_types(parameter)
        guild = interaction.guild
        for converter in self._converters(parameter.converter):
            if typing.get_origin(converter) is typing.Literal:
                for value in typing.get_args(converter):
                    yield str(value).title(), value
        if "users" in types:
            for user in self.bot.users:
                yield f"{user.display_name} ({user})", user.id
        if "members" in types:
            for member in guild.members:
                yield f"{member.display_name} ({member})", member.id
        if "roles" in types:
            for role in guild.roles:
                yield f"@{role.name}", role.id
        if "categories" in types:
            for category in guild.categories:
                yield category.name, category.id
        if "channels" in types:
            for channel in guild.text_channels:
                if channel.permissions_for(interaction.user).view_channel:
                    yield f"#{channel.name}", channel.id
