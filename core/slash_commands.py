import asyncio
import inspect
import re
import typing
from types import SimpleNamespace

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands.view import StringView

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
        self.edited_at = None
        self.attachments = [attachment] if attachment is not None else []
        self.stickers = []
        self.embeds = []
        self.mentions = []
        self.role_mentions = []
        self.channel_mentions = []
        self.message_snapshots = []
        self.reference = None
        self.type = discord.MessageType.default
        self.webhook_id = None
        self.interaction = interaction
        # Snippets and aliases copy the message. Keep acknowledgement state
        # shared so their responses are not deleted by the invocation runner.
        self._response_state = SimpleNamespace(
            sent=False,
            original_response_used=False,
            followup_started=False,
            send_lock=asyncio.Lock(),
            contexts=[],
        )
        self.slash_command_path = None
        self.slash_options = None
        self._state = interaction._state

    @property
    def response_sent(self):
        return self._response_state.sent

    @response_sent.setter
    def response_sent(self, value):
        self._response_state.sent = value

    @property
    def jump_url(self) -> str:
        # An interaction ID is not a message ID, and slash invocations do not
        # provide a user-authored message that can be linked to.
        return ""

    async def add_reaction(self, _emoji) -> None:
        # Interactions have no invocation message to react to. The runner removes
        # its deferred acknowledgement after successful, no-output callbacks.
        return None

    async def delete(self, *, delay: typing.Optional[float] = None) -> None:
        # There is no user-authored command message to remove.
        return None

    async def pin(self, *, reason: typing.Optional[str] = None) -> None:
        # There is no user-authored command message to pin.
        return None


class SlashContext(commands.Context):
    """Context that records whether a legacy callback produced a response."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.command_error_handled = asyncio.Event()
        self.response_sent = False
        self.message._response_state.contexts.append(self)

    async def send(self, content=None, **kwargs):
        private = kwargs.pop("ephemeral", False)
        state = self.message._response_state
        if self.interaction is None or self.interaction.is_expired():
            if private and self.interaction is not None:
                raise commands.CommandError("The private response expired. Run the command again.")
            message = await self.channel.send(content=content, **kwargs)
        else:
            # The first public result must fill the original public defer so
            # Discord attributes it to the invoking moderator. Private content
            # must never be the first followup, which inherits that visibility.
            async with state.send_lock:
                first = not state.followup_started
                if first and private:
                    await super().send("\u200b", ephemeral=False)
                    state.followup_started = True
                if not private and not first and not state.original_response_used:
                    message = await self._publish_original(content, kwargs)
                else:
                    message = await super().send(content, ephemeral=private, **kwargs)
                if not private:
                    state.original_response_used = True
                state.followup_started = True
        self.response_sent = True
        self.message.response_sent = True
        return message

    async def _publish_original(self, content, kwargs):
        """Replace a placeholder if private feedback preceded public output."""
        file = kwargs.get("file")
        files = kwargs.get("files")
        if file is not None and files is not None:
            raise TypeError("Cannot pass both file and files.")
        payload = {
            key: value
            for key, value in kwargs.items()
            if key in {"embed", "embeds", "view", "allowed_mentions", "poll"}
        }
        if file is not None or files is not None:
            payload["attachments"] = [file] if file is not None else files
        message = await self.interaction.edit_original_response(content=content, **payload)
        if kwargs.get("delete_after") is not None:
            await message.delete(delay=kwargs["delete_after"])
        return message


async def _parse_slash_options(command, ctx):
    """Convert named options without passing them through the positional parser."""
    # Help callbacks are already bound to a HelpCommand instance, even when
    # the command belongs to a cog. Only unbound callbacks need cog injection.
    ctx.args = [ctx]
    if command.cog is not None and not inspect.ismethod(command.callback):
        ctx.args.insert(0, command.cog)
    ctx.kwargs = {}
    for name, parameter in command.params.items():
        ctx.current_parameter = parameter
        value = ctx.message.slash_options.get(name)
        converter = parameter.converter
        greedy = isinstance(converter, commands.Greedy)
        variadic = parameter.kind == inspect.Parameter.VAR_POSITIONAL
        if value is None:
            if greedy:
                converted = []
            elif variadic:
                if command.require_var_positional:
                    raise commands.MissingRequiredArgument(parameter)
                continue
            elif parameter.required:
                raise commands.MissingRequiredArgument(parameter)
            else:
                converted = await parameter.get_default(ctx)
        else:
            # Optional's prefix-parser backtracking would silently discard an
            # invalid named option. A supplied slash value must convert.
            if typing.get_origin(converter) is typing.Union:
                alternatives = tuple(t for t in typing.get_args(converter) if t is not type(None))
                converter = typing.Union[alternatives]
            if greedy or variadic:
                view = StringView(value)
                converted = []
                while not view.eof:
                    view.skip_ws()
                    if view.eof:
                        break
                    ctx.current_argument = argument = view.get_quoted_word()
                    converted.append(
                        await commands.run_converters(
                            ctx, converter.converter if greedy else converter, argument, parameter
                        )
                    )
            else:
                ctx.current_argument = value
                converted = await commands.run_converters(ctx, converter, value, parameter)
        if variadic:
            ctx.args.extend(converted)
        elif parameter.kind == inspect.Parameter.KEYWORD_ONLY:
            ctx.kwargs[name] = converted
        else:
            ctx.args.append(converted)


def _enable_slash_options(command):
    """Add an invocation-local parser branch; leave prefix/alias parsing intact."""
    if getattr(command, "_modmail_slash_options", False):
        return
    original_parser = command._parse_arguments

    async def parse_arguments(ctx):
        if (
            isinstance(ctx, SlashContext)
            and ctx.message.slash_command_path == command.qualified_name
            and ctx.message.slash_options is not None
        ):
            await _parse_slash_options(command, ctx)
        else:
            await original_parser(ctx)

    command._parse_arguments = parse_arguments
    command._modmail_slash_options = True


class SlashCommandManager:
    """Expose prefix-style commands through Discord application commands."""

    ATTACHMENT_COMMANDS = {
        "areply",
        "fareply",
        "fpareply",
        "fpreply",
        "freply",
        "note",
        "note persistent",
        "pareply",
        "preply",
        "reply",
        "snippet add",
        "snippet edit",
        "threadmenu load_config",
    }
    REQUIRED_ATTACHMENT_COMMANDS = {"threadmenu load_config"}
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
        self._managed_commands = {}
        self._pending_guild_cleanup = set()
        self._sync_lock = asyncio.Lock()

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
                arguments = None
            await self.invoke(
                interaction,
                legacy_path,
                arguments=arguments,
                attachment=attachment,
                raw_arguments=raw_arguments,
                options=None if raw_arguments else values,
            )

        used_names = set()
        option_specs = []
        choices = {}
        if raw_arguments:
            option_specs.append(("arguments", "arguments", True, str))
        else:
            for parameter in parameters:
                display_name = self._parameter_name(parameter.name, used_names)
                required = parameter.required
                if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
                    required = command.require_var_positional
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
        if not raw_arguments:
            _enable_slash_options(command)
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
            extras={"modmail_legacy_command": legacy_group.qualified_name},
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
            extras={"modmail_legacy_command": legacy_group.qualified_name},
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

    def _build_commands(self):
        """Isolate incompatible plugin schemas before replacing registered roots."""
        roots = []
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
                leaves = command.walk_commands() if isinstance(command, app_commands.Group) else [command]
                for leaf in leaves:
                    if isinstance(leaf, app_commands.Command) and len(leaf.parameters) > 25:
                        raise ValueError(f"/{leaf.qualified_name} has more than 25 options")
            except (ValueError, TypeError, app_commands.CommandAlreadyRegistered):
                logger.exception("Skipping incompatible slash command /%s.", name)
                continue
            roots.append(command)
        return roots

    def register(self, guild: discord.Object, *, prepared=None) -> int:
        count = 0
        for command in self._build_commands() if prepared is None else prepared:
            name = command.name
            try:
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
            self._managed_commands[(guild.id, name, discord.AppCommandType.chat_input)] = command
            count += 1

        return count

    def application_command_for(self, legacy_command):
        guild_id = self.bot.inbox_guild_id
        if guild_id is None:
            return None
        matches = [
            command
            for command in self.bot.tree.walk_commands(guild=discord.Object(id=guild_id))
            if command.extras.get("modmail_legacy_command") == legacy_command.qualified_name
        ]
        # Prefer a group's intentional callback over its container or raw actions.
        return next(
            (
                c
                for c in matches
                if isinstance(c, app_commands.Command) and c.extras.get("modmail_legacy_path")
            ),
            next(iter(matches), None),
        )

    def _registry(self):
        return self.bot.config.get("slash_command_registry") or {}

    async def _save_registry(self, registry):
        self.bot.config["slash_command_registry"] = registry
        try:
            await discord.utils.maybe_coroutine(self.bot.config.update)
        except Exception:
            logger.exception("Failed to persist slash command ownership; sync will retry.")
            return False
        return True

    def _configured_guild_ids(self) -> typing.Set[int]:
        """Guilds that may contain commands from this Modmail instance."""
        return (
            self._pending_guild_cleanup
            | {int(guild_id) for guild_id in self._registry()}
            | {
                guild_id
                for guild_id in (
                    self.bot.guild_id,
                    self.bot.inbox_guild_id,
                    self._synced_guild_id,
                )
                if guild_id is not None
            }
        )

    async def _clear_guild(self, guild_id: int) -> bool:
        guild = discord.Object(id=guild_id)
        registry = dict(self._registry())
        owned = registry.get(str(guild_id), [])
        # Without a persisted command ID there is no reliable way to distinguish
        # a legacy generated command from a native plugin with the same name.
        if not owned:
            for key, command in list(self._managed_commands.items()):
                if key[0] != guild_id:
                    continue
                if self.bot.tree.get_command(key[1], guild=guild, type=key[2]) is command:
                    self.bot.tree.remove_command(key[1], guild=guild, type=key[2])
                del self._managed_commands[key]
            self._pending_guild_cleanup.discard(guild_id)
            return True
        try:
            remote_commands = {
                str(command.id): command for command in await self.bot.tree.fetch_commands(guild=guild)
            }
        except Exception:
            logger.exception("Failed to inspect slash commands in guild %s.", guild_id)
            return False
        remaining = []
        for record in owned:
            command_type = discord.AppCommandType(record["type"])
            key = (guild_id, record["name"], command_type)
            current = self.bot.tree.get_command(record["name"], guild=guild, type=command_type)
            managed = self._managed_commands.get(key)
            if current is not None and current is not managed:
                # A native plugin replaced this definition. Relinquish ownership.
                continue
            remote = remote_commands.get(record["id"])
            try:
                if remote is not None and remote.name == record["name"] and remote.type == command_type:
                    await remote.delete()
            except discord.NotFound:
                pass
            except Exception:
                logger.exception("Failed to remove /%s from guild %s.", record["name"], guild_id)
                remaining.append(record)
                continue
            if current is managed and current is not None:
                self.bot.tree.remove_command(record["name"], guild=guild, type=command_type)
            self._managed_commands.pop(key, None)
        if remaining:
            registry[str(guild_id)] = remaining
            self._pending_guild_cleanup.add(guild_id)
        else:
            registry.pop(str(guild_id), None)
            self._pending_guild_cleanup.discard(guild_id)
        saved = await self._save_registry(registry)
        return not remaining and saved

    async def sync(self, *, force: bool = False) -> None:
        async with self._sync_lock:
            await self._sync(force=force)

    async def _sync(self, *, force: bool = False) -> None:
        target_guild_id = self.bot.inbox_guild_id
        if self._synced and self._synced_guild_id == target_guild_id and not force:
            return
        self._synced = False
        if target_guild_id is None:
            logger.error(
                "Slash commands could not be synced because neither MODMAIL_GUILD_ID nor "
                "GUILD_ID is configured."
            )
            return

        # Older builds registered commands in GUILD_ID. Remove that stale
        # registry when a separate MODMAIL_GUILD_ID inbox is configured.
        self._pending_guild_cleanup.update(self._configured_guild_ids() - {target_guild_id})
        self._pending_guild_cleanup.discard(target_guild_id)
        cleared = True
        for guild_id in set(self._pending_guild_cleanup):
            cleared = await self._clear_guild(guild_id) and cleared

        guild = discord.Object(id=target_guild_id)
        prepared = self._build_commands()
        # Remove both generated commands and copied plugin commands. Track the
        # object as well as its name so a native replacement is never removed.
        for key, command in list(self._managed_commands.items()):
            guild_id, name, command_type = key
            if guild_id != target_guild_id:
                continue
            if self.bot.tree.get_command(name, guild=guild, type=command_type) is command:
                self.bot.tree.remove_command(name, guild=guild, type=command_type)
            del self._managed_commands[key]
        # Prefer any native application commands supplied by plugins. Generated
        # compatibility commands fill only the remaining names.
        for command in self.bot.tree.get_commands():
            command_type = getattr(command, "type", discord.AppCommandType.chat_input)
            if self.bot.tree.get_command(command.name, guild=guild, type=command_type) is None:
                try:
                    self.bot.tree.add_command(command, guild=guild)
                except (ValueError, TypeError, app_commands.CommandLimitReached):
                    logger.exception("Native slash command /%s could not be copied.", command.name)
                    continue
                self._managed_commands[(guild.id, command.name, command_type)] = command
        generated = self.register(guild, prepared=prepared)
        try:
            synced = await self.bot.tree.sync(guild=guild)
        except Exception:
            logger.exception("Failed to sync slash commands to guild %s.", guild.id)
            return

        registry = dict(self._registry())
        registry[str(guild.id)] = [
            {"id": str(command.id), "name": command.name, "type": command.type.value}
            for command in synced
            if (guild.id, command.name, command.type) in self._managed_commands
        ]
        saved = await self._save_registry(registry)
        self._synced = cleared and saved
        self._synced_guild_id = target_guild_id
        logger.info(
            "Synced %d slash command roots to inbox guild %s (%d generated).",
            len(synced),
            guild.id,
            generated,
        )

    async def refresh(self) -> None:
        """Refresh Discord's registry after a runtime plugin change."""
        if self._synced_guild_id is not None:
            await self.sync(force=True)

    async def disable(self) -> None:
        """Remove this instance's guild commands when slash commands are disabled."""
        async with self._sync_lock:
            await self._disable()

    async def _disable(self) -> None:
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
        self._managed_commands.clear()
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
        options: typing.Optional[typing.Dict[str, str]] = None,
    ) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True, ephemeral=False)

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
        if not raw_arguments:
            message.slash_command_path = legacy_path
            message.slash_options = options

        try:
            await self.bot.process_commands(message, cls=SlashContext)
            # Error handlers are dispatched as tasks and may await permissions
            # or network requests before sending a response.
            for context in message._response_state.contexts:
                if context.command_failed:
                    await context.command_error_handled.wait()
        except Exception:
            logger.exception("Unexpected failure while running slash command %s.", command_text)
            error_context = SlashContext(
                bot=self.bot, message=message, view=StringView(""), interaction=interaction
            )
            await error_context.send(
                "The command could not be completed. Check the bot logs for details.", ephemeral=True
            )

        if not message._response_state.original_response_used:
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
