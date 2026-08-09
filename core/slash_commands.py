import asyncio
import inspect
import re
import typing

import discord
from discord import app_commands
from discord.ext import commands

from core.models import getLogger


logger = getLogger(__name__)


class SlashCommandMessage:
    """Message-compatible view of an application-command interaction.

    The existing command callbacks intentionally continue to use
    :class:`commands.Context`. This small adapter gives the legacy parser the
    message attributes it needs while responses are handled by the interaction
    attached to :class:`SlashContext`.
    """

    def __init__(
        self,
        interaction: discord.Interaction,
        content: str,
        attachment: typing.Optional[discord.Attachment] = None,
    ):
        self.id = interaction.id
        self.author = interaction.user
        self.channel = interaction.channel
        self.guild = interaction.guild
        self.content = content
        self.created_at = interaction.created_at
        self.attachments = [attachment] if attachment is not None else []
        self.stickers = []
        self.embeds = []
        self.message_snapshots = []
        self.reference = None
        self.type = discord.MessageType.default
        self.webhook_id = None
        self.interaction = interaction
        self.response_sent = False
        self._state = interaction._state

    @property
    def jump_url(self) -> str:
        # An interaction ID is not a message ID, and slash invocations do not
        # provide a user-authored message that can be linked to.
        return ""

    async def add_reaction(self, _emoji) -> None:
        # Interactions have no invocation message to react to. The slash-command
        # runner supplies a small completion response when a callback only used
        # a reaction as its acknowledgement.
        return None

    async def delete(self, *, delay: typing.Optional[float] = None) -> None:
        # There is no user-authored command message to remove.
        return None

    async def pin(self, *, reason: typing.Optional[str] = None) -> None:
        # There is no user-authored command message to pin.
        return None


class SlashContext(commands.Context):
    """Context that records whether a legacy callback produced a response."""

    async def send(self, *args, **kwargs):
        self.message.response_sent = True
        return await super().send(*args, **kwargs)


class SlashCommandManager:
    """Expose prefix-style commands through Discord application commands."""

    ATTACHMENT_COMMANDS = {
        "areply",
        "fareply",
        "fpareply",
        "fpreply",
        "freply",
        "pareply",
        "preply",
        "reply",
        "snippet add",
        "snippet edit",
        "threadmenu load_config",
    }
    REQUIRED_ATTACHMENT_COMMANDS = {"threadmenu load_config"}
    REQUIRED_SLASH_PARAMETERS = {
        "areply": {"msg"},
        "fareply": {"msg"},
        "fpareply": {"msg"},
        "fpreply": {"msg"},
        "freply": {"msg"},
        "pareply": {"msg"},
        "preply": {"msg"},
        "reply": {"msg"},
    }
    PARAMETER_NAMES = {
        "activity_type": "activity",
        "msg": "message",
        "plugin_name": "plugin",
        "status_type": "status",
        "type_": "type",
        "user_or_role": "target",
        "users_arg": "users",
    }
    IGNORED_PARAMETERS = {"contact": {"manual_trigger"}}
    GROUP_CALLBACKS = {
        "alias": ("show", "List saved aliases or show one by name."),
        "args": ("show", "List saved reply arguments or show one by name."),
        "blocked": ("list", "List users and roles currently blocked from Modmail."),
        "debug": ("show", "Show the bot's recent application logs."),
        "logs": ("view", "View previous Modmail logs for a user."),
        "note": ("add", "Add a note to the current Modmail thread."),
        "plugins registry": ("browse", "Browse approved plugins or show one plugin."),
        "snippet": ("show", "List saved snippets or show one by name."),
    }
    # These legacy group callbacks only display prefix-command help. Discord
    # already presents their real subcommands, so exposing another action for
    # the callback would create a misleading synthetic subcommand.
    CONTAINER_ONLY_GROUPS = {
        "autotrigger",
        "config",
        "disable",
        "oauth",
        "permissions",
        "plugins",
        "threadmenu",
        "threadmenu option",
        "threadmenu submenu",
        "threadmenu submenu option",
    }
    STATIC_CHOICES = {
        ("activity", "activity_type"): (
            ("Playing", "playing"),
            ("Streaming", "streaming"),
            ("Listening", "listening"),
            ("Watching", "watching"),
            ("Competing", "competing"),
            ("Custom", "custom"),
            ("Clear activity", "clear"),
        ),
        ("close", "option"): (
            ("Silent", "silent"),
            ("Cancel scheduled close", "cancel"),
        ),
        ("permissions add", "type_"): (
            ("Command", "command"),
            ("Permission level", "level"),
        ),
        ("permissions override", "level_name"): (
            ("Owner", "owner"),
            ("Administrator", "administrator"),
            ("Moderator", "moderator"),
            ("Supporter", "supporter"),
            ("Regular", "regular"),
        ),
        ("permissions remove", "type_"): (
            ("Command", "command"),
            ("Permission level", "level"),
            ("Override", "override"),
        ),
        ("status", "status_type"): (
            ("Online", "online"),
            ("Idle", "idle"),
            ("Do Not Disturb", "dnd"),
            ("Invisible", "invisible"),
            ("Offline", "offline"),
            ("Clear status", "clear"),
        ),
        ("update", "flag"): (("Force", "force"),),
    }

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._synced = False
        self._synced_guild_id = None
        self._registered_names = set()

    @staticmethod
    def _description(command: commands.Command, fallback: typing.Optional[str] = None) -> str:
        description = fallback or command.short_doc or f"Run {command.qualified_name}."
        description = re.sub(r"\s+", " ", description).strip()
        if not description:
            description = f"Run {command.qualified_name}."
        if len(description) > 100:
            description = description[:97].rstrip() + "..."
        return description

    @staticmethod
    def _name(name: str) -> str:
        name = name.lower().replace("_", "-")
        name = re.sub(r"[^a-z0-9-]", "-", name)
        name = re.sub(r"-+", "-", name).strip("-")
        return (name or "command")[:32]

    @staticmethod
    def _unique_name(name: str, used: typing.Set[str]) -> str:
        base = SlashCommandManager._name(name)
        candidate = base
        suffix = 2
        while candidate in used:
            marker = f"-{suffix}"
            candidate = base[: 32 - len(marker)].rstrip("-") + marker
            suffix += 1
        used.add(candidate)
        return candidate

    def _parameter_name(self, parameter_name: str, used: typing.Set[str]) -> str:
        display_name = self.PARAMETER_NAMES.get(parameter_name, parameter_name)
        if display_name == "attachment":
            display_name = "value"
        return self._unique_name(display_name, used)

    def _should_register(self, command: commands.Command) -> bool:
        """Return whether a legacy command belongs in Discord's public registry."""
        if command.hidden or not command.enabled:
            return False
        if command.qualified_name != "prefix":
            return True

        config = getattr(self.bot, "config", None)
        if config is None:
            return True
        try:
            return bool(config["enable_prefix_commands"])
        except (KeyError, TypeError):
            return True

    def _group_callback(self, command: commands.Group):
        """Describe an intentional slash action for a callable legacy group."""
        name = command.extras.get("slash_callback_name")
        if name:
            description = command.extras.get("slash_callback_description")
            return str(name), description
        if command.qualified_name in self.CONTAINER_ONLY_GROUPS:
            return None
        return self.GROUP_CALLBACKS.get(command.qualified_name)

    @classmethod
    def _literal_values(cls, converter) -> typing.Tuple[typing.Any, ...]:
        if typing.get_origin(converter) is typing.Literal:
            return typing.get_args(converter)

        values = []
        for argument in typing.get_args(converter):
            if argument is type(None):
                continue
            values.extend(cls._literal_values(argument))
        return tuple(values)

    def _parameter_choices(
        self,
        command: commands.Command,
        parameter: commands.Parameter,
    ) -> typing.List[app_commands.Choice[str]]:
        configured = self.STATIC_CHOICES.get((command.qualified_name, parameter.name))
        if configured is None:
            configured = tuple(
                (str(value).replace("_", " ").title(), str(value))
                for value in self._literal_values(parameter.converter)
            )
        if len(configured) > 25 or any(
            not name or len(name) > 100 or not value or len(value) > 100 for name, value in configured
        ):
            logger.warning(
                "Ignoring invalid slash choices configured for %s.%s.",
                command.qualified_name,
                parameter.name,
            )
            return []
        return [app_commands.Choice(name=name, value=value) for name, value in configured]

    @staticmethod
    def _parameter_description(display_name: str) -> str:
        descriptions = {
            "activity": "Activity type to set, or clear the current activity.",
            "after": "Delay, duration, or message using the command's documented syntax.",
            "arguments": "Saved command name followed by any arguments.",
            "attachment": "File used by this command.",
            "body": "Python code to evaluate.",
            "category": "Category ID, mention, or name.",
            "command": "Command text to run.",
            "duration": "A human-readable duration.",
            "flag": "Optional command mode.",
            "level-name": "Permission level to assign.",
            "message": "Message text.",
            "option": "Close mode.",
            "status": "Status to set, or clear the current status.",
            "target": "User or role ID, mention, or name.",
            "type": "Permission target type.",
            "users": "One or more user or role IDs, mentions, or names.",
        }
        return descriptions.get(
            display_name,
            f"Value for {display_name.replace('-', ' ')}.",
        )

    @staticmethod
    def _quote_positional(value: str) -> str:
        if not value or any(character.isspace() for character in value) or '"' in value:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return value

    def _serialize_arguments(
        self,
        parameters: typing.Sequence[commands.Parameter],
        values: typing.Dict[str, str],
    ) -> typing.Optional[str]:
        arguments = []
        for parameter in parameters:
            value = values.get(parameter.name)
            if value is None:
                continue
            value = str(value)
            converter = parameter.converter
            greedy = converter.__class__.__name__ == "Greedy"
            if parameter.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_POSITIONAL) or greedy:
                arguments.append(value)
            else:
                arguments.append(self._quote_positional(value))
        return " ".join(arguments) or None

    def _callback(
        self,
        command: commands.Command,
        legacy_path: str,
        *,
        raw_arguments: bool,
        has_attachment: bool,
        attachment_required: bool,
    ):
        ignored = self.IGNORED_PARAMETERS.get(command.qualified_name, set())
        parameters = [
            parameter for parameter in command.clean_params.values() if parameter.name not in ignored
        ]

        async def callback(interaction, **values):
            attachment = values.pop("attachment", None)
            if raw_arguments:
                arguments = values.get("arguments")
            else:
                arguments = self._serialize_arguments(parameters, values)
            await self.invoke(
                interaction,
                legacy_path,
                arguments=arguments,
                attachment=attachment,
                raw_arguments=raw_arguments,
            )

        used_names = set()
        option_specs = []
        choices = {}
        if raw_arguments:
            option_specs.append(("arguments", "arguments", True, str))
        else:
            required_parameters = self.REQUIRED_SLASH_PARAMETERS.get(command.qualified_name, set())
            for parameter in parameters:
                display_name = self._parameter_name(parameter.name, used_names)
                required = parameter.required or parameter.name in required_parameters
                option_specs.append((parameter.name, display_name, required, str))
                parameter_choices = self._parameter_choices(command, parameter)
                if parameter_choices:
                    choices[parameter.name] = parameter_choices

        if has_attachment:
            used_names.add("attachment")
            option_specs.append(
                (
                    "attachment",
                    "attachment",
                    attachment_required,
                    discord.Attachment,
                )
            )

        # Discord requires required options before optional options. Slash
        # options are named, so this does not change legacy parsing order.
        option_specs.sort(key=lambda item: not item[2])
        signature = [
            inspect.Parameter(
                "interaction",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=discord.Interaction,
            )
        ]
        descriptions = {}
        renames = {}
        for python_name, display_name, required, annotation in option_specs:
            signature.append(
                inspect.Parameter(
                    python_name,
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=annotation if required else typing.Optional[annotation],
                    default=inspect.Parameter.empty if required else None,
                )
            )
            descriptions[python_name] = self._parameter_description(display_name)
            if python_name != display_name:
                renames[python_name] = display_name

        callback.__signature__ = inspect.Signature(signature)
        if descriptions:
            callback = app_commands.describe(**descriptions)(callback)
        if choices:
            callback = app_commands.choices(**choices)(callback)
        if renames:
            callback = app_commands.rename(**renames)(callback)
        return callback

    def _application_command(
        self,
        command: commands.Command,
        *,
        name: typing.Optional[str] = None,
        legacy_path: typing.Optional[str] = None,
        description: typing.Optional[str] = None,
        raw_arguments: bool = False,
        has_attachment: typing.Optional[bool] = None,
    ) -> app_commands.Command:
        qualified_name = command.qualified_name
        if has_attachment is None:
            has_attachment = qualified_name in self.ATTACHMENT_COMMANDS or bool(
                command.extras.get("slash_attachment")
            )
        attachment_required = qualified_name in self.REQUIRED_ATTACHMENT_COMMANDS or bool(
            command.extras.get("slash_attachment_required")
        )
        return app_commands.Command(
            name=self._name(name or command.name),
            description=self._description(command, description),
            callback=self._callback(
                command,
                legacy_path if legacy_path is not None else command.qualified_name,
                raw_arguments=raw_arguments,
                has_attachment=has_attachment,
                attachment_required=attachment_required,
            ),
            extras={
                "modmail_legacy_command": command.qualified_name,
                "modmail_legacy_path": (legacy_path if legacy_path is not None else command.qualified_name),
            },
        )

    def _add_group_callback(
        self,
        target: app_commands.Group,
        legacy_group: commands.Group,
        used: typing.Set[str],
    ) -> None:
        callback = self._group_callback(legacy_group)
        if callback is None:
            return
        name, description = callback
        target.add_command(
            self._application_command(
                legacy_group,
                name=self._unique_name(name, used),
                legacy_path=legacy_group.qualified_name,
                description=description,
            )
        )

    def _subgroup(self, legacy_group: commands.Group) -> app_commands.Group:
        subgroup = app_commands.Group(
            name=self._name(legacy_group.name),
            description=self._description(legacy_group),
        )
        used = set()
        self._add_group_callback(subgroup, legacy_group, used)

        for child in sorted(legacy_group.commands, key=lambda item: item.name):
            if isinstance(child, commands.Group) or not self._should_register(child):
                continue
            name = self._unique_name(child.name, used)
            subgroup.add_command(self._application_command(child, name=name))

        return subgroup

    def _add_hoisted_groups(
        self,
        target: app_commands.Group,
        legacy_group: commands.Group,
        name_prefix: str,
        used: typing.Set[str],
    ) -> None:
        """Hoist groups deeper than Discord's nesting limit into named sibling groups."""
        for child in sorted(legacy_group.commands, key=lambda item: item.name):
            if not isinstance(child, commands.Group) or not self._should_register(child):
                continue

            composite_name = f"{name_prefix}-{child.name}"
            subgroup = self._subgroup(child)
            if subgroup.commands:
                subgroup.name = self._unique_name(composite_name, used)
                target.add_command(subgroup)
            self._add_hoisted_groups(target, child, composite_name, used)

    def _root_group(self, legacy_group: commands.Group) -> app_commands.Group:
        group = app_commands.Group(
            name=self._name(legacy_group.name),
            description=self._description(legacy_group),
        )
        used = set()
        self._add_group_callback(group, legacy_group, used)

        for child in sorted(legacy_group.commands, key=lambda item: item.name):
            if not self._should_register(child):
                continue
            if isinstance(child, commands.Group):
                subgroup = self._subgroup(child)
                if subgroup.commands:
                    subgroup.name = self._unique_name(child.name, used)
                    group.add_command(subgroup)
                self._add_hoisted_groups(group, child, child.name, used)
                continue
            name = self._unique_name(child.name, used)
            group.add_command(self._application_command(child, name=name))

        # Saved snippet and alias names are dynamic and therefore cannot be
        # registered as Discord subcommands. These are the only intentional
        # synthetic actions in the generated tree.
        if legacy_group.name == "snippet" and "send" not in used:
            used.add("send")
            group.add_command(
                self._application_command(
                    legacy_group,
                    name="send",
                    legacy_path="",
                    description="Send a saved snippet by name.",
                    raw_arguments=True,
                )
            )
        elif legacy_group.name == "alias" and "run" not in used:
            used.add("run")
            group.add_command(
                self._application_command(
                    legacy_group,
                    name="run",
                    legacy_path="",
                    description="Run a saved command alias by name.",
                    raw_arguments=True,
                    has_attachment=True,
                )
            )

        return group

    def register(self, guild: discord.Object) -> int:
        count = 0
        used = set()

        for legacy_command in sorted(self.bot.commands, key=lambda item: item.name):
            if not self._should_register(legacy_command):
                continue
            name = self._unique_name(legacy_command.name, used)
            try:
                if isinstance(legacy_command, commands.Group):
                    command = self._root_group(legacy_command)
                    if not command.commands:
                        continue
                    command.name = name
                else:
                    command = self._application_command(legacy_command, name=name)

                existing = self.bot.tree.get_command(name, guild=guild)
                if existing is not None:
                    logger.warning(
                        "Skipping generated slash command /%s because an application command "
                        "already uses it.",
                        name,
                    )
                    continue

                self.bot.tree.add_command(command, guild=guild)
            except (app_commands.CommandAlreadyRegistered, app_commands.CommandLimitReached):
                logger.exception("Slash command /%s could not be registered.", name)
                continue
            self._registered_names.add(name)
            count += 1

        return count

    def _configured_guild_ids(self) -> typing.Set[int]:
        """Guilds that may contain commands from this Modmail instance."""
        return {
            guild_id
            for guild_id in (
                self.bot.guild_id,
                self.bot.inbox_guild_id,
                self._synced_guild_id,
            )
            if guild_id is not None
        }

    async def _clear_guild(self, guild_id: int) -> bool:
        guild = discord.Object(id=guild_id)
        self.bot.tree.clear_commands(guild=guild)
        try:
            await self.bot.tree.sync(guild=guild)
        except Exception:
            logger.exception("Failed to remove slash commands from guild %s.", guild_id)
            return False
        logger.info("Slash commands removed from guild %s.", guild_id)
        return True

    async def sync(self, *, force: bool = False) -> None:
        if self._synced and not force:
            return
        target_guild_id = self.bot.inbox_guild_id
        if target_guild_id is None:
            logger.error(
                "Slash commands could not be synced because neither MODMAIL_GUILD_ID nor "
                "GUILD_ID is configured."
            )
            return

        # Older builds registered commands in GUILD_ID. Remove that stale
        # registry when a separate MODMAIL_GUILD_ID inbox is configured.
        for guild_id in self._configured_guild_ids() - {target_guild_id}:
            await self._clear_guild(guild_id)

        guild = discord.Object(id=target_guild_id)
        if force:
            for name in self._registered_names:
                self.bot.tree.remove_command(name, guild=guild)
            self._registered_names.clear()
        # Prefer any native application commands supplied by plugins. Generated
        # compatibility commands fill only the remaining names.
        self.bot.tree.copy_global_to(guild=guild)
        generated = self.register(guild)
        try:
            synced = await self.bot.tree.sync(guild=guild)
        except Exception:
            logger.exception("Failed to sync slash commands to guild %s.", guild.id)
            return

        self._synced = True
        self._synced_guild_id = target_guild_id
        logger.info(
            "Synced %d slash command roots to inbox guild %s (%d generated).",
            len(synced),
            guild.id,
            generated,
        )

    async def refresh(self) -> None:
        """Refresh Discord's registry after a runtime plugin change."""
        if self._synced:
            await self.sync(force=True)

    async def disable(self) -> None:
        """Remove this instance's guild commands when slash commands are disabled."""
        guild_ids = self._configured_guild_ids()
        if not guild_ids:
            logger.warning(
                "Slash commands could not be removed because neither MODMAIL_GUILD_ID nor "
                "GUILD_ID is configured."
            )
            return

        removed = True
        for guild_id in guild_ids:
            removed = await self._clear_guild(guild_id) and removed

        if not removed:
            return
        self._registered_names.clear()
        self._synced = False
        self._synced_guild_id = None

    async def invoke(
        self,
        interaction: discord.Interaction,
        legacy_path: str,
        *,
        arguments: typing.Optional[str],
        attachment: typing.Optional[discord.Attachment],
        raw_arguments: bool,
    ) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)

        command_text = (arguments or "").strip() if raw_arguments else legacy_path
        if not raw_arguments and arguments and arguments.strip():
            command_text = f"{command_text} {arguments.strip()}"

        if not command_text:
            await interaction.edit_original_response(content="Please provide a command name.")
            return

        mention_prefix = f"<@{self.bot.user.id}> "
        message = SlashCommandMessage(
            interaction,
            mention_prefix + command_text,
            attachment=attachment,
        )

        try:
            await self.bot.process_commands(message, cls=SlashContext)
            # Bot event dispatch is scheduled; give command error handlers a
            # chance to send their interaction response before the fallback.
            await asyncio.sleep(0)
        except Exception:
            logger.exception("Unexpected failure while running slash command %s.", command_text)
            if not message.response_sent:
                await interaction.edit_original_response(
                    content="The command could not be completed. Check the bot logs for details."
                )
            return

        if not message.response_sent:
            # Commands such as /reply acknowledge prefix invocations with a
            # reaction. A slash interaction has no message to react to, so its
            # deferred response is only transport-level bookkeeping. Removing
            # it keeps successful, no-output commands out of the channel while
            # preserving real command responses and errors.
            try:
                await interaction.delete_original_response()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                logger.warning(
                    "Failed to remove the acknowledgement for slash command %s.",
                    command_text,
                    exc_info=True,
                )
