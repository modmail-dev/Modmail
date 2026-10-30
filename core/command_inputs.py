"""Command prompts that also work without the message-content intent."""

import asyncio
from types import SimpleNamespace

import discord
from discord.ext import commands

from core.slash_commands import SlashContext


class AuthorView(discord.ui.View):
    def __init__(self, author_id, *, timeout=120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the command author can use this prompt.", ephemeral=True
            )
            return False
        return True


class ConfirmationView(AuthorView):
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def accept(self, interaction, button):
        await interaction.response.edit_message(view=None)
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(view=None)
        self.value = False
        self.stop()


class ReplyModal(discord.ui.Modal, title="Command input"):
    answer = discord.ui.TextInput(label="Response", style=discord.TextStyle.paragraph, max_length=4000)

    def __init__(self, prompt):
        super().__init__(timeout=prompt.timeout)
        self.prompt = prompt

    async def interaction_check(self, interaction):
        return await self.prompt.interaction_check(interaction)

    async def on_submit(self, interaction):
        prompt = self.prompt
        if prompt.is_finished():
            await interaction.response.send_message("This prompt has expired.", ephemeral=True)
            return
        reply = SimpleNamespace(
            content=self.answer.value, author=prompt.ctx.author, channel=prompt.ctx.channel
        )
        if reply.content.strip().lower() != "cancel" and not await discord.utils.maybe_coroutine(
            prompt.check, reply
        ):
            await interaction.response.send_message(
                "Invalid response. Use Enter response to try again.", ephemeral=True
            )
            return
        await interaction.response.defer()
        if not prompt.result.done():
            prompt.result.set_result(reply)
        prompt.stop()


class ReplyView(AuthorView):
    def __init__(self, ctx, check, *, timeout):
        super().__init__(ctx.author.id, timeout=timeout)
        self.ctx = ctx
        self.check = check
        self.result = asyncio.get_running_loop().create_future()

    @discord.ui.button(label="Enter response", style=discord.ButtonStyle.primary)
    async def enter(self, interaction, button):
        await interaction.response.send_modal(ReplyModal(self))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(view=None)
        if not self.result.done():
            self.result.set_result(
                SimpleNamespace(content="cancel", author=self.ctx.author, channel=self.ctx.channel)
            )
        self.stop()


async def _remove_controls(message, view):
    view.stop()
    try:
        await message.edit(view=None)
    except discord.HTTPException:
        pass


async def wait_for_reply(ctx, *, check=None, timeout=None):
    """Return a message-shaped response from a modal, or a legacy text reply."""
    if check is None:
        check = lambda message: message.author == ctx.author and message.channel == ctx.channel
    if not isinstance(ctx, SlashContext):
        return await ctx.bot.wait_for("message", check=check, timeout=timeout)
    timeout = 120 if timeout is None else timeout
    view = ReplyView(ctx, check, timeout=timeout)
    message = await ctx.send("Use the button to answer the previous question.", view=view)
    try:
        return await asyncio.wait_for(view.result, timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise commands.BadArgument("The prompt timed out. Run the command again.") from exc
    finally:
        await _remove_controls(message, view)


async def confirm(ctx, prompt, *, timeout=30, confirmation_word="confirm"):
    if not isinstance(ctx, SlashContext):
        await ctx.send(prompt + f"\nType `{confirmation_word}` to confirm, or anything else to cancel.")
        reply = await ctx.bot.wait_for(
            "message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel, timeout=timeout
        )
        return reply.content.strip().lower() == confirmation_word
    view = ConfirmationView(ctx.author.id, timeout=timeout)
    message = await ctx.send(prompt, view=view)
    try:
        if await view.wait():
            raise asyncio.TimeoutError
        return view.value is True
    finally:
        await _remove_controls(message, view)
