import discord
import asyncio


class PaginatorSession:
    """
    Class that interactively paginates a set of embeds

    Parameters
    ------------
    ctx: Context
        The context of the command.
    timeout:
        How long to wait for before the session closes
    embeds: List[discord.Embed]
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
    def __init__(self, ctx, *embeds, **options):
        self.ctx = ctx
        self.timeout = options.get('timeout', 60)
        self.embeds = embeds
        self.running = False
        self.base = None
        self.current = 0
        self.reaction_map = {
            '⏮': self.first_page,
            '◀': self.previous_page,
            '▶': self.next_page,
            '⏭': self.last_page,
            # '⏹': self.close
        }

        if options.get('edit_footer', True) and len(self.embeds) > 1:
            for i, em in enumerate(self.embeds):
                footer_text = f'Page {i+1} of {len(self.embeds)}'
                if em.footer.text:
                    footer_text = footer_text + ' • ' + em.footer.text
                em.set_footer(text=footer_text, icon_url=em.footer.icon_url)

    def add_page(self, embed):
        if isinstance(embed, discord.Embed):
            self.embeds.append(embed)
        else:
            raise TypeError('Page must be an Embed object.')

    async def create_base(self, embed):
        self.base = await self.ctx.send(embed=embed)

        if len(self.embeds) == 1:
            self.running = False
            return

        self.running = True
        for reaction in self.reaction_map.keys():
            if len(self.embeds) == 2 and reaction in '⏮⏭':
                continue
            await self.base.add_reaction(reaction)

    async def show_page(self, index: int):
        if not 0 <= index < len(self.embeds):
            return

        self.current = index
        page = self.embeds[index]

        if self.running:
            await self.base.edit(embed=page)
        else:
            await self.create_base(page)

    def react_check(self, reaction, user):
        return reaction.message.id == self.base.id and user.id == self.ctx.author.id and reaction.emoji in self.reaction_map.keys()

    async def run(self):
        if not self.running:
            await self.show_page(0)
        while self.running:
            try:
                reaction, user = await self.ctx.bot.wait_for('reaction_add', check=self.react_check, timeout=self.timeout)
            except asyncio.TimeoutError:
                self.paginating = False
                await self.close(delete=False)
            else:
                action = self.reaction_map.get(reaction.emoji)
                await action()
            try:
                await self.base.remove_reaction(reaction, user)
            except:
                pass

    def previous_page(self):
        """Go to the previous page."""
        return self.show_page(self.current - 1)

    def next_page(self):
        """Go to the next page"""
        return self.show_page(self.current + 1)

    async def close(self, delete=True):
        """Delete this embed."""
        self.running = False

        try:
            await self.ctx.message.add_reaction('✅')
        except:
            pass

        if delete:
            return await self.base.delete()

        try:
            await self.base.clear_reactions()
        except:
            pass

    def first_page(self):
        """Go to immediately to the first page"""
        return self.show_page(0)

    def last_page(self):
        """Go to immediately to the last page"""
        return self.show_page(len(self.embeds) - 1)
