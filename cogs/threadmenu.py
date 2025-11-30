import json
import asyncio
from copy import copy as _copy

import discord
from discord.ext import commands

from core import checks
from core.models import PermissionLevel


class ThreadCreationMenuCore(commands.Cog):
    """Core-integrated thread menu configuration and management.

    This Cog exposes the same commands as the legacy plugin to manage menu options,
    but stores settings in core config (no plugin DB).
    """

    def __init__(self, bot):
        self.bot = bot

    # ----- helpers -----
    def _get_conf(self) -> dict:
        return {
            "enabled": bool(self.bot.config.get("thread_creation_menu_enabled")),
            "options": self.bot.config.get("thread_creation_menu_options") or {},
            "submenus": self.bot.config.get("thread_creation_menu_submenus") or {},
            "timeout": int(self.bot.config.get("thread_creation_menu_timeout") or 20),
            "close_on_timeout": bool(self.bot.config.get("thread_creation_menu_close_on_timeout")),
            "anonymous_menu": bool(self.bot.config.get("thread_creation_menu_anonymous_menu")),
            "embed_text": self.bot.config.get("thread_creation_menu_embed_text")
            or "Please select an option.",
            "dropdown_placeholder": self.bot.config.get("thread_creation_menu_dropdown_placeholder")
            or "Select an option to contact the staff team.",
            "embed_title": self.bot.config.get("thread_creation_menu_embed_title"),
            "embed_footer": self.bot.config.get("thread_creation_menu_embed_footer"),
            "embed_thumbnail_url": self.bot.config.get("thread_creation_menu_embed_thumbnail_url"),
            "embed_footer_icon_url": self.bot.config.get("thread_creation_menu_embed_footer_icon_url"),
            "embed_color": self.bot.config.get("thread_creation_menu_embed_color"),
        }

    async def _save_conf(self, conf: dict):
        await self.bot.config.set("thread_creation_menu_enabled", conf.get("enabled", False))
        await self.bot.config.set("thread_creation_menu_options", conf.get("options", {}), convert=False)
        await self.bot.config.set("thread_creation_menu_submenus", conf.get("submenus", {}), convert=False)
        await self.bot.config.set("thread_creation_menu_timeout", conf.get("timeout", 20))
        await self.bot.config.set(
            "thread_creation_menu_close_on_timeout", conf.get("close_on_timeout", False)
        )
        await self.bot.config.set("thread_creation_menu_anonymous_menu", conf.get("anonymous_menu", False))
        await self.bot.config.set(
            "thread_creation_menu_embed_text", conf.get("embed_text", "Please select an option.")
        )
        await self.bot.config.set(
            "thread_creation_menu_dropdown_placeholder",
            conf.get("dropdown_placeholder", "Select an option to contact the staff team."),
        )
        await self.bot.config.set("thread_creation_menu_embed_title", conf.get("embed_title"))
        await self.bot.config.set("thread_creation_menu_embed_footer", conf.get("embed_footer"))
        await self.bot.config.set("thread_creation_menu_embed_thumbnail_url", conf.get("embed_thumbnail_url"))
        await self.bot.config.set(
            "thread_creation_menu_embed_footer_icon_url", conf.get("embed_footer_icon_url")
        )
        if conf.get("embed_color"):
            try:
                await self.bot.config.set("thread_creation_menu_embed_color", conf.get("embed_color"))
            except Exception:
                pass
        await self.bot.config.update()

    # ----- commands -----
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.group(invoke_without_command=True)
    async def threadmenu(self, ctx):
        """Thread-creation menu settings (core)."""
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu.command(name="toggle")
    async def threadmenu_toggle(self, ctx):
        """Enable or disable the thread-creation menu.

        Toggles the global on/off state. When disabled, users won't see
        or be able to use the interactive thread creation select menu.
        """
        conf = self._get_conf()
        conf["enabled"] = not conf["enabled"]
        await self._save_conf(conf)
        await ctx.send(f"Thread-creation menu is now {'enabled' if conf['enabled'] else 'disabled'}.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu.command(name="show")
    async def threadmenu_show(self, ctx):
        """Show all current main-menu options.

        Lists every option (label + description) configured in the root
        (non-submenu) select menu so you can review what users will see.
        """
        conf = self._get_conf()
        if not conf["options"]:
            return await ctx.send("There are no options in the main menu.")
        embed = discord.Embed(title="Main menu", color=discord.Color.blurple())
        for v in conf["options"].values():
            embed.add_field(name=v["label"], value=v["description"], inline=False)
        await ctx.send(embed=embed)

    # ----- options -----
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu.group(name="option", invoke_without_command=True)
    async def threadmenu_option(self, ctx):
        """Manage main-menu options (add/remove/edit/show).

        Use subcommands:
        - add: interactive wizard to create an option
        - remove <label>: delete an option
        - edit <label>: interactively modify an option
        - show <label>: display full details (type, command/submenu, emoji)
        """
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_option.command(name="show")
    async def threadmenu_option_show(self, ctx, *, label: str):
        """Show detailed information about a main-menu option."""
        conf = self._get_conf()
        key = label.lower().replace(" ", "_")
        if key not in conf["options"]:
            return await ctx.send("That label does not exist.")
        v = conf["options"][key]
        embed = discord.Embed(title=v["label"], color=discord.Color.blurple())
        embed.add_field(name="Description", value=v["description"], inline=False)
        embed.add_field(name="Emoji", value=v["emoji"], inline=False)
        embed.add_field(name="Type", value=v["type"], inline=False)
        embed.add_field(
            name=("Command" if v["type"] == "command" else "Submenu"), value=v["callback"], inline=False
        )
        # Show category if set
        cat_id = v.get("category_id")
        if cat_id:
            guild = self.bot.modmail_guild or ctx.guild
            category = guild and guild.get_channel(cat_id)
            cat_name = getattr(category, "name", "Unknown/Deleted")
            embed.add_field(name="Category", value=f"{cat_name} (ID: {cat_id})", inline=False)
        else:
            embed.add_field(name="Category", value="Default (main category)", inline=False)
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_option.command(name="add")
    async def threadmenu_option_add(self, ctx):
        """Interactive wizard to add a main-menu option."""
        conf = self._get_conf()

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        def typecheck(m):
            return (
                m.author == ctx.author
                and m.channel == ctx.channel
                and m.content.lower()
                in [
                    "command",
                    "submenu",
                ]
            )

        if len(conf["options"]) >= 25:
            return await ctx.send("You can only have a maximum of 25 options due to discord limitations.")

        await ctx.send(
            "You can type `skip` for non-required steps or `cancel` to cancel the process at any time."
        )
        await ctx.send("What is the label of the option?")
        label = (await self.bot.wait_for("message", check=check)).content
        sanitized_label = label.lower().replace(" ", "_")

        if label.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if sanitized_label in conf["options"]:
            await ctx.send("That option already exists. Use `threadmenu edit` to edit it.")
            return

        await ctx.send("What is the description of the option? (not required)")
        description = (await self.bot.wait_for("message", check=check)).content

        if description.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if len(description) > 100:
            return await ctx.send(
                "The description must be less than 100 characters due to discord limitations."
            )

        if description.lower() == "skip":
            description = None

        await ctx.send("What is the emoji of the option? (not required)")
        emoji = (await self.bot.wait_for("message", check=check)).content

        if emoji.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if emoji.lower() == "skip":
            emoji = None

        await ctx.send("What is the type of the option? (command/submenu)")
        type_ = (await self.bot.wait_for("message", check=typecheck)).content.lower()

        if type_ == "cancel":
            return await ctx.send("Cancelled.")

        if type_ == "command":
            await ctx.send("What is the command to run for the option?")
        else:
            await ctx.send("What is the label of the submenu for the option?")
        callback = (await self.bot.wait_for("message", check=check)).content
        if type_ != "command":
            callback = callback.lower().replace(" ", "_")

        if callback.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if type_ == "submenu" and callback not in conf["submenus"]:
            return await ctx.send("That submenu does not exist. Use `threadmenu submenu create` to add it.")

        # Optional: category where the thread should be created when this option is chosen
        await ctx.send(
            "Optionally provide a category for threads created via this option (mention, ID, or name).\n"
            "Type `default` to use the main category."
        )
        category_msg = await self.bot.wait_for("message", check=check)
        category_raw = category_msg.content.strip()
        category_id: int | None = None
        if category_raw.lower() == "cancel":
            return await ctx.send("Cancelled.")
        if category_raw.lower() not in {"", "default", "none", "skip"}:
            guild = self.bot.modmail_guild or ctx.guild
            resolved = None
            try:
                # Try ID
                if category_raw.isdigit():
                    resolved = guild.get_channel(int(category_raw)) if guild else None
                # Try mention <#id> is not valid for categories; fall back to name search
                if not resolved and guild:
                    resolved = discord.utils.find(
                        lambda c: isinstance(c, discord.CategoryChannel)
                        and c.name.lower() == category_raw.lower(),
                        guild.categories,
                    )
            except Exception:
                resolved = None
            if isinstance(resolved, discord.CategoryChannel):
                category_id = resolved.id
            else:
                await ctx.send(
                    "Couldn't resolve that category. I'll default to the main category for this option."
                )

        conf["options"][sanitized_label] = {
            "label": label,
            "description": description,
            "emoji": emoji,
            "type": type_,
            "callback": callback,
            "category_id": category_id,
        }
        await self._save_conf(conf)
        await ctx.send("Option added.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_option.command(name="remove")
    async def threadmenu_option_remove(self, ctx, *, label: str):
        """Remove a main-menu option by label."""
        conf = self._get_conf()
        key = label.lower().replace(" ", "_")
        if key not in conf["options"]:
            return await ctx.send("That option does not exist.")
        del conf["options"][key]
        await self._save_conf(conf)
        await ctx.send("Option removed.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_option.command(name="edit")
    async def threadmenu_option_edit(self, ctx, *, label: str):
        """Interactive wizard to edit a main-menu option."""
        conf = self._get_conf()
        key = label.lower().replace(" ", "_")
        if key not in conf["options"]:
            return await ctx.send("That option does not exist.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        def typecheck(m):
            return (
                m.author == ctx.author
                and m.channel == ctx.channel
                and m.content.lower()
                in [
                    "command",
                    "submenu",
                ]
            )

        await ctx.send(
            "You can type `skip` for non-required steps (uses previous value) or `cancel` to cancel the process at any time."
            "Use `none` to clear the value for non-required steps."
        )
        await ctx.send("What is the new description of the option? (not required)")
        description = (await self.bot.wait_for("message", check=check)).content
        if description.lower() == "cancel":
            return await ctx.send("Cancelled.")

        old_description = conf["options"][key]["description"]

        if description.lower() == "skip":
            description = old_description
        elif description.lower() == "none":
            description = None
        else:
            if len(description) > 100:
                return await ctx.send(
                    "The description must be less than 100 characters due to discord limitations."
                )

        await ctx.send("What is the new emoji of the option?")
        emoji = (await self.bot.wait_for("message", check=check)).content
        if emoji.lower() == "cancel":
            return await ctx.send("Cancelled.")

        old_emoji = conf["options"][key].get("emoji")

        if emoji.lower() == "skip":
            emoji = old_emoji
        elif emoji.lower() == "none":
            emoji = None

        await ctx.send("What is the new type of the option? (command/submenu)")
        type_ = (await self.bot.wait_for("message", check=typecheck)).content.lower()
        if type_ == "cancel":
            return await ctx.send("Cancelled.")

        if type_ == "command":
            await ctx.send("What is the new command to run for the option?")
        else:
            await ctx.send("What is the new label of the new submenu for the option?")
        callback = (await self.bot.wait_for("message", check=check)).content
        if type_ != "command":
            callback = callback.lower().replace(" ", "_")
        if callback.lower() == "cancel":
            return await ctx.send("Cancelled.")
        if type_ == "submenu" and callback not in conf["submenus"]:
            return await ctx.send("That submenu does not exist. Use `threadmenu submenu create` to add it.")

        # Category edit (optional)
        await ctx.send(
            "Optionally provide a new category for this option (mention, ID, or name).\n"
            "Send `skip` to keep current setting; send `default` or `none` to clear."
        )
        cat_msg = await self.bot.wait_for("message", check=check)
        cat_raw = cat_msg.content.strip()
        if cat_raw.lower() == "cancel":
            return await ctx.send("Cancelled.")

        current = conf["options"][key].get("category_id")
        new_category_id = current
        if cat_raw.lower() in {"default", "none"}:
            new_category_id = None
        elif cat_raw.lower() in {"", "skip"}:
            new_category_id = current
        else:
            guild = self.bot.modmail_guild or ctx.guild
            resolved = None
            try:
                if cat_raw.isdigit():
                    resolved = guild.get_channel(int(cat_raw)) if guild else None
                if not resolved and guild:
                    resolved = discord.utils.find(
                        lambda c: isinstance(c, discord.CategoryChannel)
                        and c.name.lower() == cat_raw.lower(),
                        guild.categories,
                    )
            except Exception:
                resolved = None
            if isinstance(resolved, discord.CategoryChannel):
                new_category_id = resolved.id
            else:
                await ctx.send("Couldn't resolve that category. Keeping previous setting.")

        old_label = conf["options"][key]["label"]
        conf["options"][key] = {
            "label": old_label,
            "description": description,
            "emoji": emoji,
            "type": type_,
            "callback": callback,
            "category_id": new_category_id,
        }
        await self._save_conf(conf)
        await ctx.send("Option edited.")

    # ----- submenus -----
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu.group(name="submenu", invoke_without_command=True)
    async def threadmenu_submenu(self, ctx):
        """Manage submenus (create/delete/list/show and options within).

        Submenus let you branch the initial select menu into additional
        categorized option groups. Use `submenu option` subcommands to
        manage the nested options.
        """
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_submenu.command(name="create")
    async def threadmenu_submenu_create(self, ctx, *, label: str):
        """Create an empty submenu that can hold nested options."""
        conf = self._get_conf()
        key = label.lower().replace(" ", "_")
        if key in conf["submenus"]:
            return await ctx.send(
                "That submenu already exists. Please use a unique label or use `threadmenu submenu delete` to delete it."
            )
        conf["submenus"][key] = {}
        await self._save_conf(conf)
        await ctx.send("Submenu created.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_submenu.command(name="delete")
    async def threadmenu_submenu_delete(self, ctx, *, label: str):
        """Delete a submenu and all its options."""
        conf = self._get_conf()
        key = label.lower().replace(" ", "_")
        if key not in conf["submenus"]:
            return await ctx.send("That submenu does not exist.")
        del conf["submenus"][key]
        await self._save_conf(conf)
        await ctx.send("Submenu deleted.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_submenu.command(name="list")
    async def threadmenu_submenu_list(self, ctx):
        """List all submenu keys currently configured."""
        conf = self._get_conf()
        if not conf["submenus"]:
            return await ctx.send("There are no submenus.")
        submenu_list = "Submenus:\n" + ("\n".join(conf["submenus"].keys()))
        if len(submenu_list) > 2000:
            submenu_list = submenu_list[:1997] + "..."
        await ctx.send(submenu_list)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_submenu.command(name="show")
    async def threadmenu_submenu_show(self, ctx, *, label: str):
        """Show the options configured inside a submenu."""
        conf = self._get_conf()
        key = label.lower().replace(" ", "_")
        if key not in conf["submenus"]:
            return await ctx.send("That submenu does not exist. Use `threadmenu submenu create` to add it.")
        if not conf["submenus"][key]:
            return await ctx.send(f"There are no options in {key}")
        embed = discord.Embed(title=key, color=discord.Color.blurple())
        for v in conf["submenus"][key].values():
            embed.add_field(name=v["label"], value=v["description"], inline=False)
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_submenu.group(name="option", invoke_without_command=True)
    async def threadmenu_submenu_option(self, ctx):
        """Manage options within a specific submenu (add/remove/edit)."""
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_submenu_option.command(name="add")
    async def threadmenu_submenu_option_add(self, ctx, *, submenu: str):
        """Interactive wizard to add an option inside a submenu."""
        conf = self._get_conf()
        submenu = submenu.lower().replace(" ", "_")
        if submenu not in conf["submenus"]:
            return await ctx.send("That submenu does not exist.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        def typecheck(m):
            return (
                m.author == ctx.author
                and m.channel == ctx.channel
                and m.content.lower()
                in [
                    "command",
                    "submenu",
                ]
            )

        if len(conf["submenus"][submenu]) >= 24:
            return await ctx.send("You can only have a maximum of 24 options due to discord limitations.")

        await ctx.send(
            "You can type `skip` for non-required steps or `cancel` to cancel the process at any time."
        )
        await ctx.send("What is the label of the option?")
        label = (await self.bot.wait_for("message", check=check)).content
        sanitized_label = label.lower().replace(" ", "_")

        if label.lower() == "cancel":
            return await ctx.send("Cancelled.")
        if label.lower() == "main menu":
            return await ctx.send("You cannot use that label.")
        if sanitized_label in conf["submenus"][submenu]:
            await ctx.send("That option already exists. Use `threadmenu submenu edit` to edit it.")
            return

        await ctx.send("What is the description of the option? (not required)")
        description = (await self.bot.wait_for("message", check=check)).content
        if description.lower() == "cancel":
            return await ctx.send("Cancelled.")
        if len(description) > 100:
            return await ctx.send(
                "The description must be less than 100 characters due to discord limitations."
            )

        if description.lower() == "skip":
            description = None

        await ctx.send("What is the emoji of the option? (not required)")
        emoji = (await self.bot.wait_for("message", check=check)).content
        if emoji.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if emoji.lower() == "skip":
            emoji = None

        await ctx.send("What is the type for the option? (command/submenu)")
        type_ = (await self.bot.wait_for("message", check=typecheck)).content.lower()
        if type_ == "cancel":
            return await ctx.send("Cancelled.")

        if type_ == "command":
            await ctx.send("What is the command to run for the option?")
        else:
            await ctx.send("What is the label of the submenu for the option?")
        callback = (await self.bot.wait_for("message", check=check)).content
        if type_ != "command":
            callback = callback.lower().replace(" ", "_")
        if type_ == "submenu" and callback not in conf["submenus"]:
            return await ctx.send("That submenu does not exist. Use `threadmenu submenu create` to add it.")

        # Optional category for submenu option
        await ctx.send(
            "Optionally provide a category for threads created via this submenu option (mention, ID, or name).\n"
            "Type `default` to use the main category."
        )
        category_msg = await self.bot.wait_for("message", check=check)
        category_raw = category_msg.content.strip()
        category_id: int | None = None
        if category_raw.lower() == "cancel":
            return await ctx.send("Cancelled.")
        if category_raw.lower() not in {"", "default", "none", "skip"}:
            guild = self.bot.modmail_guild or ctx.guild
            resolved = None
            try:
                if category_raw.isdigit():
                    resolved = guild.get_channel(int(category_raw)) if guild else None
                if not resolved and guild:
                    resolved = discord.utils.find(
                        lambda c: isinstance(c, discord.CategoryChannel)
                        and c.name.lower() == category_raw.lower(),
                        guild.categories,
                    )
            except Exception:
                resolved = None
            if isinstance(resolved, discord.CategoryChannel):
                category_id = resolved.id
            else:
                await ctx.send(
                    "Couldn't resolve that category. I'll default to the main category for this submenu option."
                )

        conf["submenus"][submenu][sanitized_label] = {
            "label": label,
            "description": description,
            "emoji": emoji,
            "type": type_,
            "callback": callback,
            "category_id": category_id,
        }
        await self._save_conf(conf)
        await ctx.send("Option added.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_submenu_option.command(name="remove")
    async def threadmenu_submenu_option_remove(self, ctx, *, submenu: str):
        """Remove an option from a submenu via an interactive prompt."""
        conf = self._get_conf()
        submenu = submenu.lower().replace(" ", "_")
        if submenu not in conf["submenus"]:
            return await ctx.send("That submenu does not exist.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send("You can send `cancel` at any time to cancel the process.")
        await ctx.send("What is the label of the option to remove?")
        label = (await self.bot.wait_for("message", check=check)).content
        key = label.lower().replace(" ", "_")
        if label.lower() == "cancel":
            return await ctx.send("Cancelled.")
        if key not in conf["submenus"][submenu]:
            return await ctx.send("That option does not exist.")

        del conf["submenus"][submenu][key]
        await self._save_conf(conf)
        await ctx.send("Option removed.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu_submenu_option.command(name="edit")
    async def threadmenu_submenu_option_edit(self, ctx, *, submenu: str):
        """Interactive wizard to edit a submenu option."""
        conf = self._get_conf()
        submenu = submenu.lower().replace(" ", "_")
        if submenu not in conf["submenus"]:
            return await ctx.send("That submenu does not exist. Use `threadmenu submenu create` to add it.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        def typecheck(m):
            return (
                m.author == ctx.author
                and m.channel == ctx.channel
                and m.content.lower()
                in [
                    "command",
                    "submenu",
                ]
            )

        await ctx.send(
            "You can type `skip` for non-required steps (uses previous value) or `cancel` to cancel the process at any time."
            "Use `none` to clear the value for non-required steps."
        )
        await ctx.send("What is the label of the option to edit?")
        label = (await self.bot.wait_for("message", check=check)).content
        key = label.lower().replace(" ", "_")
        if label.lower() == "cancel":
            return await ctx.send("Cancelled.")
        if key not in conf["submenus"][submenu]:
            return await ctx.send("That label does not exist.")

        await ctx.send("What is the new description of the option? (not required)")
        description = (await self.bot.wait_for("message", check=check)).content
        if description.lower() == "cancel":
            return await ctx.send("Cancelled.")

        option_data = conf["submenus"][submenu][key]
        old_description = option_data.get("description")

        if description.lower() == "skip":
            description = old_description
        elif description.lower() == "none":
            description = None
        else:
            if len(description) > 100:
                return await ctx.send(
                    "The description must be less than 100 characters due to discord limitations."
                )

        await ctx.send("What is the new emoji of the option? (not required)")
        emoji = (await self.bot.wait_for("message", check=check)).content
        if emoji.lower() == "cancel":
            return await ctx.send("Cancelled.")

        old_emoji = option_data.get("emoji")

        if emoji.lower() == "skip":
            emoji = old_emoji
        elif emoji.lower() == "none":
            emoji = None

        await ctx.send("What is the new type for the option? (command/submenu)")
        type_ = (await self.bot.wait_for("message", check=typecheck)).content.lower()
        if type_ == "cancel":
            return await ctx.send("Cancelled.")

        if type_ == "command":
            await ctx.send("What is the command to run for the option?")
        else:
            await ctx.send("What is the label of the submenu for the option?")
        callback = (await self.bot.wait_for("message", check=check)).content
        if type_ != "command":
            callback = callback.lower().replace(" ", "_")
        if callback.lower() == "cancel":
            return await ctx.send("Cancelled.")
        if type_ == "submenu" and callback not in conf["submenus"]:
            return await ctx.send("That submenu does not exist.")

        # Category edit (optional)
        await ctx.send(
            "Optionally provide a new category for this submenu option (mention, ID, or name).\n"
            "Send `skip` to keep current setting; send `default` or `none` to clear."
        )
        cat_msg = await self.bot.wait_for("message", check=check)
        cat_raw = cat_msg.content.strip()
        if cat_raw.lower() == "cancel":
            return await ctx.send("Cancelled.")
        current = conf["submenus"][submenu][key].get("category_id")
        new_category_id = current
        if cat_raw.lower() in {"default", "none"}:
            new_category_id = None
        elif cat_raw.lower() in {"", "skip"}:
            new_category_id = current
        else:
            guild = self.bot.modmail_guild or ctx.guild
            resolved = None
            try:
                if cat_raw.isdigit():
                    resolved = guild.get_channel(int(cat_raw)) if guild else None
                if not resolved and guild:
                    resolved = discord.utils.find(
                        lambda c: isinstance(c, discord.CategoryChannel)
                        and c.name.lower() == cat_raw.lower(),
                        guild.categories,
                    )
            except Exception:
                resolved = None
            if isinstance(resolved, discord.CategoryChannel):
                new_category_id = resolved.id
            else:
                await ctx.send("Couldn't resolve that category. Keeping previous setting.")

        conf["submenus"][submenu][key]["description"] = description
        conf["submenus"][submenu][key]["emoji"] = emoji
        conf["submenus"][submenu][key]["type"] = type_
        conf["submenus"][submenu][key]["callback"] = callback
        conf["submenus"][submenu][key]["category_id"] = new_category_id
        await self._save_conf(conf)
        await ctx.send("Option edited.")

    # ----- import/export -----
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu.command(name="dump_config")
    async def threadmenu_dump_config(self, ctx):
        """Dump the current core thread menu config to a file."""
        conf = self._get_conf()
        with open("thread_creation_menu_config.json", "w", encoding="utf-8") as f:
            json.dump(conf, f, indent=4)
        await ctx.send(file=discord.File("thread_creation_menu_config.json"))

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu.command(name="reset")
    async def threadmenu_reset(self, ctx):
        """Reset ALL thread-creation menu settings to their defaults.

        This clears options and submenus and restores every key starting with
        `thread_creation_menu_` back to the default values. Confirmation required.
        This action is irreversible.
        """
        warning = (
            "This will clear ALL thread menu options, submenus, and related settings and restore defaults.\n"
            "This action is irreversible. Type `confirm` within 30 seconds to proceed, or anything else to cancel."
        )
        await ctx.send(warning)

        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            return await ctx.send("Timed out — reset cancelled.")

        if reply.content.strip().lower() != "confirm":
            return await ctx.send("Reset cancelled.")

        # Reset all `thread_creation_menu_` keys to defaults
        defaults = getattr(self.bot.config, "defaults", {})
        keys = [k for k in defaults.keys() if k.startswith("thread_creation_menu_")]

        # Ensure we handle mappings without unwanted conversion
        for k in keys:
            v = defaults[k]
            if k in {"thread_creation_menu_options", "thread_creation_menu_submenus"}:
                await self.bot.config.set(k, v, convert=False)
            else:
                await self.bot.config.set(k, v)

        # Also disable the menu explicitly for clarity
        await self.bot.config.set("thread_creation_menu_enabled", False)
        await self.bot.config.update()

        await ctx.send(
            f"Thread-creation menu configuration has been reset to defaults (reset {len(keys)} keys)."
        )

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @threadmenu.command(name="load_config")
    async def threadmenu_load_config(self, ctx):
        """Load the thread menu config from an attached file."""
        if not ctx.message.attachments:
            return await ctx.send("You must attach a json file to load the config from.")
        b = await ctx.message.attachments[0].read()
        json_data = b.decode("utf-8")
        try:
            data = json.loads(json_data)
        except json.decoder.JSONDecodeError:
            return await ctx.send("Invalid json file.")

        # minimal validation
        required = {
            "enabled",
            "options",
            "submenus",
            "timeout",
            "close_on_timeout",
            "anonymous_menu",
            "embed_text",
            "dropdown_placeholder",
        }
        if not required.issubset(set(data.keys())):
            return await ctx.send("Config file missing required keys.")

        await self._save_conf(data)
        await ctx.send("Successfully loaded config into core.")


async def setup(bot):
    await bot.add_cog(ThreadCreationMenuCore(bot))
