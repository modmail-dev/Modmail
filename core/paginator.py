import typing

import discord
from discord import Message, Embed, ButtonStyle, Interaction
from discord.ui import View, Button, Select
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
    callback_map : Dict[str, method]
        A mapping for text to method.
    view : PaginatorView
        The view that is sent along with the base message.
    select_menu : Select
        A select menu that will be added to the View.
    """

    def __init__(self, ctx: commands.Context, *pages, **options):
        self.ctx = ctx
        self.timeout: int = options.get("timeout", 210)
        self.running = False
        self.base: Message = None
        self.current = 0
        self.pages = list(pages)
        self.destination = options.get("destination", ctx)
        self.view = None
        self.select_menu = None

        self.callback_map = {
            "<<": self.first_page,
            "<": self.previous_page,
            ">": self.next_page,
            ">>": self.last_page,
        }
        self._buttons_map = {"<<": None, "<": None, ">": None, ">>": None}

    async def show_page(self, index: int) -> typing.Optional[typing.Dict]:
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
        result = None

        if self.running:
            result = self._show_page(page)
        else:
            await self.create_base(page)

        self.update_disabled_status()
        return result

    def update_disabled_status(self):
        if self.current == self.first_page():
            # disable << button
            if self._buttons_map["<<"] is not None:
                self._buttons_map["<<"].disabled = True

            if self._buttons_map["<"] is not None:
                self._buttons_map["<"].disabled = True
        else:
            if self._buttons_map["<<"] is not None:
                self._buttons_map["<<"].disabled = False

            if self._buttons_map["<"] is not None:
                self._buttons_map["<"].disabled = False

        if self.current == self.last_page():
            # disable >> button
            if self._buttons_map[">>"] is not None:
                self._buttons_map[">>"].disabled = True

            if self._buttons_map[">"] is not None:
                self._buttons_map[">"].disabled = True
        else:
            if self._buttons_map[">>"] is not None:
                self._buttons_map[">>"].disabled = False

            if self._buttons_map[">"] is not None:
                self._buttons_map[">"].disabled = False

    async def create_base(self, item) -> None:
        """
        Create a base `Message`.
        """
        if len(self.pages) == 1:
            self.view = None
            self.running = False
        else:
            self.view = PaginatorView(self, timeout=self.timeout)
            self.update_disabled_status()
            self.running = True

        await self._create_base(item, self.view)

    async def _create_base(self, item, view: View) -> None:
        raise NotImplementedError

    def _show_page(self, page):
        raise NotImplementedError

    def first_page(self):
        """Returns the index of the first page"""
        return 0

    def next_page(self):
        """Returns the index of the next page"""
        return min(self.current + 1, self.last_page())

    def previous_page(self):
        """Returns the index of the previous page"""
        return max(self.current - 1, self.first_page())

    def last_page(self):
        """Returns the index of the last page"""
        return len(self.pages) - 1

    async def run(self) -> typing.Optional[Message]:
        """
        Starts the pagination session.
        """
        if not self.running:
            await self.show_page(self.current)

            if self.view is not None:
                await self.view.wait()

            await self.close(delete=False)

    async def close(
        self, delete: bool = True, *, interaction: Interaction = None
    ) -> typing.Optional[Message]:
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
        if self.running:
            sent_emoji, _ = await self.ctx.bot.retrieve_emoji()
            await self.ctx.bot.add_reaction(self.ctx.message, sent_emoji)

            if interaction:
                message = interaction.message
            else:
                message = self.base

            self.running = False

            if self.view is not None:
                self.view.stop()
                if delete:
                    await message.delete()
                else:
                    self.view.clear_items()
                    await message.edit(view=self.view)


class PaginatorView(View):
    """
    View that is used for pagination.

    Parameters
    ----------
    handler : PaginatorSession
        The paginator session that spawned this view.
    timeout : float
        How long to wait for before the session closes.

    Attributes
    ----------
    handler : PaginatorSession
        The paginator session that spawned this view.
    timeout : float
        How long to wait for before the session closes.
    """

    def __init__(self, handler: PaginatorSession, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = handler
        self.clear_items()  # clear first so we can control the order
        self.fill_items()

    @discord.ui.button(label="Stop", style=ButtonStyle.danger)
    async def stop_button(self, interaction: Interaction, button: Button):
        await self.handler.close(interaction=interaction)

    def fill_items(self):
        if self.handler.select_menu is not None:
            self.add_item(self.handler.select_menu)

        for label, callback in self.handler.callback_map.items():
            if len(self.handler.pages) == 2 and label in ("<<", ">>"):
                continue

            if label in ("<<", ">>"):
                style = ButtonStyle.secondary
            else:
                style = ButtonStyle.primary

            button = PageButton(self.handler, callback, label=label, style=style)

            self.handler._buttons_map[label] = button
            self.add_item(button)
        self.add_item(self.stop_button)

    async def interaction_check(self, interaction: Interaction):
        """Only allow the message author to interact"""
        if interaction.user != self.handler.ctx.author:
            await interaction.response.send_message(
                "Only the original author can control this!", ephemeral=True
            )
            return False
        return True


class PageButton(Button):
    """
    A button that has a callback to jump to the next page

    Parameters
    ----------
    handler : PaginatorSession
        The paginator session that spawned this view.
    page_callback : Callable
        A callable that returns an int of the page to go to.

    Attributes
    ----------
    handler : PaginatorSession
        The paginator session that spawned this view.
    page_callback : Callable
        A callable that returns an int of the page to go to.
    """

    def __init__(self, handler, page_callback, **kwargs):
        super().__init__(**kwargs)
        self.handler = handler
        self.page_callback = page_callback

    async def callback(self, interaction: Interaction):
        kwargs = await self.handler.show_page(self.page_callback())
        await interaction.response.edit_message(**kwargs, view=self.view)


class PageSelect(Select):
    def __init__(self, handler: PaginatorSession, pages: typing.List[typing.Tuple[str]]):
        self.handler = handler
        options = []
        for n, (label, description) in enumerate(pages):
            options.append(discord.SelectOption(label=label, description=description, value=str(n)))

        options = options[:25]  # max 25 options
        super().__init__(placeholder="Select a page", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        page = int(self.values[0])
        kwargs = await self.handler.show_page(page)
        await interaction.response.edit_message(**kwargs, view=self.view)


class EmbedPaginatorSession(PaginatorSession):
    def __init__(self, ctx: commands.Context, *embeds, **options):
        super().__init__(ctx, *embeds, **options)

        if len(self.pages) > 1:
            select_options = []
            create_select = True
            for i, embed in enumerate(self.pages):
                footer_text = f"Page {i + 1} of {len(self.pages)}"
                if embed.footer.text:
                    footer_text = footer_text + " • " + embed.footer.text

                if embed.footer.icon:
                    icon_url = embed.footer.icon.url
                else:
                    icon_url = None
                embed.set_footer(text=footer_text, icon_url=icon_url)

                # select menu
                if embed.author.name:
                    title = embed.author.name[:30].strip()
                    if len(embed.author.name) > 30:
                        title += "..."
                else:
                    title = embed.title[:30].strip()
                    if len(embed.title) > 30:
                        title += "..."
                    if not title:
                        create_select = False

                if embed.description:
                    description = embed.description[:40].replace("*", "").replace("`", "").strip()
                    if len(embed.description) > 40:
                        description += "..."
                else:
                    description = ""
                select_options.append((title, description))

            if create_select:
                if len(set(x[0] for x in select_options)) != 1:  # must have unique authors
                    self.select_menu = PageSelect(self, select_options)

    def add_page(self, item: Embed) -> None:
        if isinstance(item, Embed):
            self.pages.append(item)
        else:
            raise TypeError("Page must be an Embed object.")

    async def _create_base(self, item: Embed, view: View) -> None:
        self.base = await self.destination.send(embed=item, view=view)

    def _show_page(self, page):
        return dict(embed=page)


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

            if self.embed.footer.icon:
                icon_url = self.embed.footer.icon.url
            else:
                icon_url = None

            self.embed.set_footer(text=footer_text, icon_url=icon_url)

    async def _create_base(self, item: str, view: View) -> None:
        self._set_footer()
        self.base = await self.ctx.send(content=item, embed=self.embed, view=view)

    def _show_page(self, page) -> typing.Dict:
        self._set_footer()
        return dict(content=page, embed=self.embed)
