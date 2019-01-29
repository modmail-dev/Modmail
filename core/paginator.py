import typing
from asyncio import TimeoutError

from discord import Embed, Message, HTTPException, InvalidArgument
from discord.ext import commands


class PaginatorSession:
    """
    Class that interactively paginates a set of embeds

    Parameters
    ------------
    ctx: Context
        The context of the command.
    timeout:
        How long to wait for before the session closes
    embeds: List[Embed]
        A list of entries to paginate.

    Methods
    -------
    add_page:
        Add an embed to paginate
    run:
        Run the interactive session
    close:
        Forcefully destroy a session
    """

    def __init__(self, ctx: commands.Context, *embeds, **options):
        self.ctx = ctx
        self.timeout: int = options.get('timeout', 60)
        self.embeds: typing.List[Embed] = list(embeds)
        self.running = False
        self.base: Message = None
        self.current = 0
        self.reaction_map = {
            '⏮': self.first_page,
            '◀': self.previous_page,
            '▶': self.next_page,
            '⏭': self.last_page,
            # '⏹': self.close
        }

        if options.get('edit_footer', True) and len(self.embeds) > 1:
            for i, embed in enumerate(self.embeds):
                footer_text = f'Page {i + 1} of {len(self.embeds)}'
                if embed.footer.text:
                    footer_text = footer_text + ' • ' + embed.footer.text
                embed.set_footer(text=footer_text,
                                 icon_url=embed.footer.icon_url)

    def add_page(self, embed: Embed) -> None:
        if isinstance(embed, Embed):
            self.embeds.append(embed)
        else:
            raise TypeError('Page must be an Embed object.')

    async def create_base(self, embed: Embed) -> None:
        self.base = await self.ctx.send(embed=embed)

        if len(self.embeds) == 1:
            self.running = False
            return

        self.running = True
        for reaction in self.reaction_map:
            if len(self.embeds) == 2 and reaction in '⏮⏭':
                continue
            await self.base.add_reaction(reaction)

    async def show_page(self, index: int) -> None:
        if not 0 <= index < len(self.embeds):
            return

        self.current = index
        page = self.embeds[index]

        if self.running:
            await self.base.edit(embed=page)
        else:
            await self.create_base(page)

    def react_check(self, reaction, user) -> bool:
        return reaction.message.id == self.base.id and \
               user.id == self.ctx.author.id and \
               reaction.emoji in self.reaction_map.keys()

    async def run(self) -> typing.Optional[Message]:
        if not self.running:
            await self.show_page(0)
        while self.running:
            try:
                reaction, user = await self.ctx.bot.wait_for(
                    'reaction_add',
                    check=self.react_check,
                    timeout=self.timeout
                )
            except TimeoutError:
                return await self.close(delete=False)
            else:
                action = self.reaction_map.get(reaction.emoji)
                await action()
            try:
                await self.base.remove_reaction(reaction, user)
            except (HTTPException, InvalidArgument):
                pass

    async def previous_page(self) -> None:
        """Go to the previous page."""
        await self.show_page(self.current - 1)

    async def next_page(self) -> None:
        """Go to the next page"""
        await self.show_page(self.current + 1)

    async def close(self, delete: bool = True) -> typing.Optional[Message]:
        """Delete this embed."""
        self.running = False

        try:
            await self.ctx.message.add_reaction('✅')
        except (HTTPException, InvalidArgument):
            pass

        if delete:
            return await self.base.delete()

        try:
            await self.base.clear_reactions()
        except HTTPException:
            pass

    async def first_page(self) -> None:
        """Go to immediately to the first page"""
        await self.show_page(0)

    async def last_page(self) -> None:
        """Go to immediately to the last page"""
        await self.show_page(len(self.embeds) - 1)
