import typing
from asyncio import TimeoutError

from discord import User, Reaction, Message, Embed
from discord import HTTPException, InvalidArgument
from discord.ext import commands


class PaginatorSession:
    """
    Class that interactively paginates a list of `Embed`.

    Parameters
    ----------
    ctx : Context
        The context of the command.
    timeout : float
        How long to wait for before the session closes.
    embeds : List[Embed]
        A list of entries to paginate.
    edit_footer : bool, optional
        Whether to set the footer.
        Defaults to `True`.

    Attributes
    ----------
    ctx : Context
        The context of the command.
    timeout : float
        How long to wait for before the session closes.
    embeds : List[Embed]
        A list of entries to paginate.
    running : bool
        Whether the paginate session is running.
    base : Message
        The `Message` of the `Embed`.
    current : int
        The current page number.
    reaction_map : Dict[str, meth]
        A mapping for reaction to method.

    """

    def __init__(self, ctx: commands.Context, *embeds, **options):
        self.ctx = ctx
        self.timeout: int = options.get('timeout', 180)
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
        """
        Add a `Embed` page.

        Parameters
        ----------
        embed : Embed
            The `Embed` to add.
        """
        if isinstance(embed, Embed):
            self.embeds.append(embed)
        else:
            raise TypeError('Page must be an Embed object.')

    async def create_base(self, embed: Embed) -> None:
        """
        Create a base `Message`.

        Parameters
        ----------
        embed : Embed
            The `Embed` to fill the base `Message`.
        """
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
        """
        Show a page by page number.

        Parameters
        ----------
        index : int
            The index of the page.
        """
        if not 0 <= index < len(self.embeds):
            return

        self.current = index
        page = self.embeds[index]

        if self.running:
            await self.base.edit(embed=page)
        else:
            await self.create_base(page)

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
        return (reaction.message.id == self.base.id and
                user.id == self.ctx.author.id and
                reaction.emoji in self.reaction_map.keys())

    async def run(self) -> typing.Optional[Message]:
        """
        Starts the pagination session.

        Returns
        -------
        Optional[Message]
            If it's closed before running ends.
        """
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
        """
        Go to the first page.
        """
        await self.show_page(0)

    async def last_page(self) -> None:
        """
        Go to the last page.
        """
        await self.show_page(len(self.embeds) - 1)


class MessagePaginatorSession:
    def __init__(self, ctx: commands.Context, *messages,
                 embed: Embed = None, **options):
        self.ctx = ctx
        self.timeout: int = options.get('timeout', 180)
        self.messages: typing.List[str] = list(messages)

        self.running = False
        self.base: Message = None
        self.embed = embed
        if embed is not None:
            self.footer_text = self.embed.footer.text
        else:
            self.footer_text = None

        self.current = 0
        self.reaction_map = {
            '⏮': self.first_page,
            '◀': self.previous_page,
            '▶': self.next_page,
            '⏭': self.last_page,
            # '⏹': self.close
        }

    def add_page(self, msg: str) -> None:
        """
        Add a message page.

        Parameters
        ----------
        msg : str
            The message to add.
        """
        if isinstance(msg, str):
            self.messages.append(msg)
        else:
            raise TypeError('Page must be a str object.')

    async def create_base(self, msg: str) -> None:
        """
        Create a base `Message`.

        Parameters
        ----------
        msg : str
            The message content to fill the base `Message`.
        """
        if self.embed is not None:
            footer_text = f'Page 1 of {len(self.messages)}'
            if self.footer_text:
                footer_text = footer_text + ' • ' + self.footer_text
            self.embed.set_footer(text=footer_text,
                                  icon_url=self.embed.footer.icon_url)

        self.base = await self.ctx.send(content=msg, embed=self.embed)

        if len(self.messages) == 1:
            self.running = False
            return

        self.running = True
        for reaction in self.reaction_map:
            if len(self.messages) == 2 and reaction in '⏮⏭':
                continue
            await self.base.add_reaction(reaction)

    async def show_page(self, index: int) -> None:
        """
        Show a page by page number.

        Parameters
        ----------
        index : int
            The index of the page.
        """
        if not 0 <= index < len(self.messages):
            return

        self.current = index
        page = self.messages[index]

        if self.embed is not None:
            footer_text = f'Page {self.current + 1} of {len(self.messages)}'
            if self.footer_text:
                footer_text = footer_text + ' • ' + self.footer_text
            self.embed.set_footer(text=footer_text,
                                  icon_url=self.embed.footer.icon_url)

        if self.running:
            await self.base.edit(content=page, embed=self.embed)
        else:
            await self.create_base(page)

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
        return (reaction.message.id == self.base.id and
                user.id == self.ctx.author.id and
                reaction.emoji in self.reaction_map.keys())

    async def run(self) -> typing.Optional[Message]:
        """
        Starts the pagination session.

        Returns
        -------
        Optional[Message]
            If it's closed before running ends.
        """
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
        """
        Go to the first page.
        """
        await self.show_page(0)

    async def last_page(self) -> None:
        """
        Go to the last page.
        """
        await self.show_page(len(self.messages) - 1)
