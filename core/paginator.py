import typing
import asyncio

from discord import User, Reaction, Message, Embed
from discord import HTTPException, InvalidArgument
from discord.ext import commands


class PaginatorSession:
    """
    Class that interactively paginates something.

    Parameters
    ----------
    ctx : Context
        The context of the command.
    timeout : float
        How long to wait for before the session closes.
    pages : List[Any]
        A list of entries to paginate.

    Attributes
    ----------
    ctx : Context
        The context of the command.
    timeout : float
        How long to wait for before the session closes.
    pages : List[Any]
        A list of entries to paginate.
    running : bool
        Whether the paginate session is running.
    base : Message
        The `Message` of the `Embed`.
    current : int
        The current page number.
    reaction_map : Dict[str, method]
        A mapping for reaction to method.
    """

    def __init__(self, ctx: commands.Context, *pages, **options):
        self.ctx = ctx
        self.timeout: int = options.get("timeout", 210)
        self.running = False
        self.base: Message = None
        self.current = 0
        self.pages = list(pages)
        self.destination = options.get("destination", ctx)
        self.reaction_map = {
            "⏮": self.first_page,
            "◀": self.previous_page,
            "▶": self.next_page,
            "⏭": self.last_page,
            "🛑": self.close,
        }

    def add_page(self, item) -> None:
        """
        Add a page.
        """
        raise NotImplementedError

    async def create_base(self, item) -> None:
        """
        Create a base `Message`.
        """
        await self._create_base(item)

        if len(self.pages) == 1:
            self.running = False
            return

        self.running = True
        for reaction in self.reaction_map:
            if len(self.pages) == 2 and reaction in "⏮⏭":
                continue
            await self.ctx.bot.add_reaction(self.base, reaction)

    async def _create_base(self, item) -> None:
        raise NotImplementedError

    async def show_page(self, index: int) -> None:
        """
        Show a page by page number.

        Parameters
        ----------
        index : int
            The index of the page.
        """
        if not 0 <= index < len(self.pages):
            return

        self.current = index
        page = self.pages[index]

        if self.running:
            await self._show_page(page)
        else:
            await self.create_base(page)

    async def _show_page(self, page):
        raise NotImplementedError

    def react_check(self, reaction: Reaction, user: User) -> bool:
        """

        Parameters
        ----------
        reaction : Reaction
            The `Reaction` object of the reaction.
        user : User
            The `User` or `Member` object of who sent the reaction.

        Returns
        -------
        bool
        """
        return (
            reaction.message.id == self.base.id
            and user.id == self.ctx.author.id
            and reaction.emoji in self.reaction_map.keys()
        )

    async def run(self) -> typing.Optional[Message]:
        """
        Starts the pagination session.

        Returns
        -------
        Optional[Message]
            If it's closed before running ends.
        """
        if not self.running:
            await self.show_page(self.current)
        while self.running:
            try:
                reaction, user = await self.ctx.bot.wait_for(
                    "reaction_add", check=self.react_check, timeout=self.timeout
                )
            except asyncio.TimeoutError:
                return await self.close(delete=False)
            else:
                action = self.reaction_map.get(reaction.emoji)
                await action()
            try:
                await self.base.remove_reaction(reaction, user)
            except (HTTPException, InvalidArgument):
                pass

    async def previous_page(self) -> None:
        """
        Go to the previous page.
        """
        await self.show_page(self.current - 1)

    async def next_page(self) -> None:
        """
        Go to the next page.
        """
        await self.show_page(self.current + 1)

    async def close(self, delete: bool = True) -> typing.Optional[Message]:
        """
        Closes the pagination session.

        Parameters
        ----------
        delete : bool, optional
            Whether or delete the message upon closure.
            Defaults to `True`.

        Returns
        -------
        Optional[Message]
            If `delete` is `True`.
        """
        self.running = False

        sent_emoji, _ = await self.ctx.bot.retrieve_emoji()
        await self.ctx.bot.add_reaction(self.ctx.message, sent_emoji)

        if delete:
            return await self.base.delete()

        try:
            await self.base.clear_reactions()
        except HTTPException:
            pass

    async def first_page(self) -> None:
        """
        Go to the first page.
        """
        await self.show_page(0)

    async def last_page(self) -> None:
        """
        Go to the last page.
        """
        await self.show_page(len(self.pages) - 1)


class EmbedPaginatorSession(PaginatorSession):
    def __init__(self, ctx: commands.Context, *embeds, **options):
        super().__init__(ctx, *embeds, **options)

        if len(self.pages) > 1:
            for i, embed in enumerate(self.pages):
                footer_text = f"Page {i + 1} of {len(self.pages)}"
                if embed.footer.text:
                    footer_text = footer_text + " • " + embed.footer.text
                embed.set_footer(text=footer_text, icon_url=embed.footer.icon_url)

    def add_page(self, item: Embed) -> None:
        if isinstance(item, Embed):
            self.pages.append(item)
        else:
            raise TypeError("Page must be an Embed object.")

    async def _create_base(self, item: Embed) -> None:
        self.base = await self.destination.send(embed=item)

    async def _show_page(self, page):
        await self.base.edit(embed=page)


class MessagePaginatorSession(PaginatorSession):
    def __init__(self, ctx: commands.Context, *messages, embed: Embed = None, **options):
        self.embed = embed
        self.footer_text = self.embed.footer.text if embed is not None else None
        super().__init__(ctx, *messages, **options)

    def add_page(self, item: str) -> None:
        if isinstance(item, str):
            self.pages.append(item)
        else:
            raise TypeError("Page must be a str object.")

    def _set_footer(self):
        if self.embed is not None:
            footer_text = f"Page {self.current+1} of {len(self.pages)}"
            if self.footer_text:
                footer_text = footer_text + " • " + self.footer_text
            self.embed.set_footer(text=footer_text, icon_url=self.embed.footer.icon_url)

    async def _create_base(self, item: str) -> None:
        self._set_footer()
        self.base = await self.ctx.send(content=item, embed=self.embed)

    async def _show_page(self, page) -> None:
        self._set_footer()
        await self.base.edit(content=page, embed=self.embed)
