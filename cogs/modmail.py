import asyncio
from datetime import datetime
from typing import Optional, Union

import discord
from discord.ext import commands

import re

from dateutil import parser
from natural.date import duration

from core import checks
from core.decorators import trigger_typing
from core.models import Bot
from core.paginator import PaginatorSession
from core.time import UserFriendlyTime, human_timedelta
from core.utils import format_preview, User


class Modmail:
    """Commandes directement liées à la fonctionnalité Modmail."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command()
    @trigger_typing
    @checks.has_permissions(administrator=True)
    async def setup(self, ctx):
        """Configure un serveur pour le ModMail"""
        if self.bot.main_category:
            return await ctx.send(
                f'{self.bot.modmail_guild} est déjà configuré.'
            )

        category = await self.bot.modmail_guild.create_category(
            name='Discord.FR',
            overwrites=self.bot.overwrites(ctx)
        )

        await category.edit(position=0)

        log_channel = await self.bot.modmail_guild.create_text_channel(
            name='bot-logs', category=category
        )

        embed = discord.Embed(
            title='Petit rappel:',
            description='Vous pouvez utiliser le `config set log_channel_id '
                        '<channel-id>` commande pour configurer un canal de journal personnalisé'
                        ', alors vous pouvez supprimer la valeur par défaut '
                        f'{log_channel.mention} salon.',
            color=self.bot.main_color
        )

        embed.set_footer(text=f'Taper "{self.bot.prefix}help" '
                              'pour une liste complète des commandes.')
        await log_channel.send(embed=embed)

        self.bot.config['main_category_id'] = category.id
        self.bot.config['log_channel_id'] = log_channel.id

        await self.bot.config.update()
        await ctx.send('Serveur configuré avec succès.')

    @commands.group()
    @checks.has_permissions(manage_messages=True)
    async def snippets(self, ctx):
        """Renvoie une liste des snippets actuellement définis."""
        if ctx.invoked_subcommand is not None:
            return

        embeds = []

        if self.bot.snippets:
            embed = discord.Embed(color=self.bot.main_color,
                                  description='Voici une liste de snippets '
                                              'qui sont actuellement configurés.')
        else:
            embed = discord.Embed(
                color=discord.Color.red(),
                description="Vous n'avez pas de snippets pour le moment."
            )
            embed.set_footer(
                text=f'Tapez {self.bot.prefix}help snippets pour plus de commandes.'
            )

        embed.set_author(name='Snippets', icon_url=ctx.guild.icon_url)
        embeds.append(embed)

        for name, value in self.bot.snippets.items():
            if len(embed.fields) == 5:
                embed = discord.Embed(color=self.bot.main_color,
                                      description=embed.description)
                embed.set_author(name='Snippets', icon_url=ctx.guild.icon_url)
                embeds.append(embed)
            embed.add_field(name=name, value=value, inline=False)

        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @snippets.command(name='add')
    @checks.has_permissions(manage_messages=True)
    async def add_(self, ctx, name: str.lower, *, value):
        """Ajoutez un snippet à la configuration du bot."""
        if 'snippets' not in self.bot.config.cache:
            self.bot.config['snippets'] = {}

        self.bot.config.snippets[name] = value
        await self.bot.config.update()

        embed = discord.Embed(
            title='Snippet ajoutée',
            color=self.bot.main_color,
            description=f'`{name}` pointe vers: {value}'
        )

        await ctx.send(embed=embed)

    @snippets.command(name='del')
    @checks.has_permissions(manage_messages=True)
    async def del_(self, ctx, *, name: str.lower):
        """Supprime un snippet de bot config."""

        if self.bot.config.snippets.get(name):
            embed = discord.Embed(
                title='Snippet supprimée',
                color=self.bot.main_color,
                description=f"`{name}` n'existe plus."
            )
            del self.bot.config['snippets'][name]
            await self.bot.config.update()

        else:
            embed = discord.Embed(
                title='Erreur',
                color=discord.Color.red(),
                description=f"Snippet `{name}` n'existe pas."
            )

        await ctx.send(embed=embed)

    @commands.command()
    @checks.has_permissions(manage_messages=True)
    async def move(self, ctx, *, category: discord.CategoryChannel):
        """Déplace un ticket dans une catégorie spécifiée."""
        thread = ctx.thread
        if not thread:
            embed = discord.Embed(
                title='Erreur',
                description="Ce n'est pas un fil Modmail.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        await thread.channel.edit(category=category, sync_permissions=True)
        await ctx.message.add_reaction('✅')

    @staticmethod
    async def send_scheduled_close_message(ctx, after, silent=False):
        human_delta = human_timedelta(after.dt)

        silent = '*silencieusement* ' if silent else ''

        embed = discord.Embed(
            title='Fermeture prévue',
            description=f'Ce ticket se fermera {silent}dans {human_delta}.',
            color=discord.Color.red()
        )

        if after.arg and not silent:
            embed.add_field(name='Message', value=after.arg)

        embed.set_footer(text='La fermeture sera annulée '
                              'si un message de discussion est envoyé.')
        embed.timestamp = after.dt

        await ctx.send(embed=embed)

    @commands.command(usage='[after] [close message]')
    @checks.thread_only()
    async def close(self, ctx, *, after: UserFriendlyTime = None):
        """
        Fermer le ticket actuel.

        Fermer après une période de temps:
        - `close in 5 hours`
        - `close 2m30s`

        Messages de fermeture personnalisés:
        - `close 2 hours Le problème a été résolu.`
        - `close Nous vous contacterons dès que nous en saurons plus.`

        Fermer silencieusement un fil de discussion (pas de message)
        - `close silently`
        - `close in 10m silently`

        Empêcher un fil de se fermer:
        - `close cancel`
        """

        thread = ctx.thread

        now = datetime.utcnow()

        close_after = (after.dt - now).total_seconds() if after else 0
        message = after.arg if after else None
        silent = str(message).lower() in {'silent', 'silently'}
        cancel = str(message).lower() == 'cancel'

        if cancel:

            if thread.close_task is not None:
                await thread.cancel_closure()
                embed = discord.Embed(color=discord.Color.red(),
                                      description='La fermeture prévue '
                                                  'a été annulé.')
            else:
                embed = discord.Embed(
                    color=discord.Color.red(),
                    description="Ce fil n'a pas encore été "
                                'programmé pour se fermer.'
                )

            return await ctx.send(embed=embed)

        if after and after.dt > now:
            await self.send_scheduled_close_message(ctx, after, silent)

        await thread.close(
            closer=ctx.author,
            after=close_after,
            message=message,
            silent=silent,
        )

    @commands.command(aliases=['alert'])
    @checks.thread_only()
    async def notify(self, ctx, *, role=None):
        """
        Avertissez un rôle ou vous-même au prochain ticket ouvert.

        Vous serez notifié une fois dès qu'un ticket est ouvert.
        """
        thread = ctx.thread

        if not role:
            mention = ctx.author.mention
        elif role.lower() in ('here', 'everyone'):
            mention = '@' + role
        else:
            converter = commands.RoleConverter()
            role = await converter.convert(ctx, role)
            mention = role.mention

        if str(thread.id) not in self.bot.config['notification_squad']:
            self.bot.config['notification_squad'][str(thread.id)] = []

        mentions = self.bot.config['notification_squad'][str(thread.id)]

        if mention in mentions:
            embed = discord.Embed(color=discord.Color.red(),
                                  description=f'{mention} va déjà '
                                  'être mentionné.')
        else:
            mentions.append(mention)
            await self.bot.config.update()
            embed = discord.Embed(color=self.bot.main_color,
                                  description=f'{mention} sera mentionné dans '
                                  'le prochain ticket.')
        return await ctx.send(embed=embed)

    @commands.command(aliases=['sub'])
    @checks.thread_only()
    async def subscribe(self, ctx, *, role=None):
        """
        Avertissez-vous ou indiquez un rôle pour chaque message reçu dans ce ticket.

        Vous recevrez un ping pour chaque message reçu 
        dans ce ticket jusqu'à votre désinscription (unsubscribe).
        """
        thread = ctx.thread

        if not role:
            mention = ctx.author.mention
        elif role.lower() in ('here', 'everyone'):
            mention = '@' + role
        else:
            converter = commands.RoleConverter()
            role = await converter.convert(ctx, role)
            mention = role.mention

        if str(thread.id) not in self.bot.config['subscriptions']:
            self.bot.config['subscriptions'][str(thread.id)] = []

        mentions = self.bot.config['subscriptions'][str(thread.id)]

        if mention in mentions:
            embed = discord.Embed(color=discord.Color.red(),
                                  description=f'{mention} est déjà '
                                  'abonné à ce ticket.')
        else:
            mentions.append(mention)
            await self.bot.config.update()
            embed = discord.Embed(
                color=self.bot.main_color,
                description=f'{mention} sera maintenant '
                'notifié pour tous les messages reçus dans ce ticket.'
            )
        return await ctx.send(embed=embed)

    @commands.command(aliases=['unsub'])
    @checks.thread_only()
    async def unsubscribe(self, ctx, *, role=None):
        """Désabonnez-vous ou un rôle dans un ticket."""
        thread = ctx.thread

        if not role:
            mention = ctx.author.mention
        elif role.lower() in ('here', 'everyone'):
            mention = '@' + role
        else:
            converter = commands.RoleConverter()
            role = await converter.convert(ctx, role)
            mention = role.mention

        if str(thread.id) not in self.bot.config['subscriptions']:
            self.bot.config['subscriptions'][str(thread.id)] = []

        mentions = self.bot.config['subscriptions'][str(thread.id)]

        if mention not in mentions:
            embed = discord.Embed(color=discord.Color.red(),
                                  description=f"{mention} n'est pas "
                                  'abonné à ce ticket.')
        else:
            mentions.remove(mention)
            await self.bot.config.update()
            embed = discord.Embed(color=self.bot.main_color,
                                  description=f'{mention} est maintenant désabonné '
                                  'à ce ticket.')
        return await ctx.send(embed=embed)

    @commands.command()
    @checks.thread_only()
    async def nsfw(self, ctx):
        """Marque un ticket comme nsfw."""
        await ctx.channel.edit(nsfw=True)
        await ctx.message.add_reaction('✅')

    @commands.command()
    @checks.thread_only()
    async def loglink(self, ctx):
        """Renvoie le lien des logs du ticket actuel."""
        log_link = await self.bot.api.get_log_link(ctx.channel.id)
        await ctx.send(
            embed=discord.Embed(
                color=self.bot.main_color,
                description=log_link
            )
        )

    def format_log_embeds(self, logs, avatar_url):
        embeds = []
        logs = tuple(logs)
        title = f'Total des résultats trouvés ({len(logs)})'

        for entry in logs:

            key = entry['key']

            created_at = parser.parse(entry['created_at'])

            log_url = (
                f"https://support.discord.fr/{key}"
                if not self.bot.self_hosted else
                self.bot.config.log_url.strip('/') + f'/logs/{key}'
            )

            username = entry['recipient']['name'] + '#'
            username += entry['recipient']['discriminator']

            embed = discord.Embed(color=self.bot.main_color,
                                  timestamp=created_at)
            embed.set_author(name=f'{title} - {username}',
                             icon_url=avatar_url,
                             url=log_url)
            embed.url = log_url
            embed.add_field(name='Créé',
                            value=duration(created_at, now=datetime.utcnow()))
            embed.add_field(name='Fermé par',
                            value=f"<@{entry['closer']['id']}>")

            if entry['recipient']['id'] != entry['creator']['id']:
                embed.add_field(name='Créé par',
                                value=f"<@{entry['creator']['id']}>")

            embed.add_field(name='Aperçu',
                            value=format_preview(entry['messages']),
                            inline=False)
            embed.add_field(name='Lien', value=log_url)
            embed.set_footer(
                text='ID destinataire: ' + str(entry['recipient']['id'])
            )
            embeds.append(embed)
        return embeds

    @commands.group(invoke_without_command=True)
    @checks.has_permissions(manage_messages=True)
    async def logs(self, ctx, *, member: User = None):
        """Affiche une liste des tickets support d'un membre."""

        await ctx.trigger_typing()

        if not member:
            thread = ctx.thread
            if not thread:
                raise commands.UserInputError
            user = thread.recipient
        else:
            user = member

        default_avatar = 'https://cdn.discordapp.com/embed/avatars/0.png'
        icon_url = getattr(user, 'avatar_url', default_avatar)

        logs = await self.bot.api.get_user_logs(user.id)

        if not any(not log['open'] for log in logs):
            embed = discord.Embed(color=discord.Color.red(),
                                  description="Cet utilisateur n'a pas "
                                              "n'a pas eu de ticket.")
            return await ctx.send(embed=embed)

        logs = reversed([e for e in logs if not e['open']])

        embeds = self.format_log_embeds(logs, avatar_url=icon_url)

        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @logs.command(name='closed-by')
    @checks.has_permissions(manage_messages=True)
    async def closed_by(self, ctx, *, user: User = None):
        """Renvoie tous les ticket fermés par un utilisateur."""
        if not self.bot.self_hosted:
            embed = discord.Embed(
                color=discord.Color.red(),
                description='Cette commande ne fonctionne '
                            'que si vous auto-hébergez vos logs.'
                )
            return await ctx.send(embed=embed)

        user = user or ctx.author

        query = {
            'guild_id': str(self.bot.guild_id),
            'open': False,
            'closer.id': str(user.id)
        }

        projection = {
            'messages': {'$slice': 5}
        }

        entries = await self.bot.db.logs.find(query, projection).to_list(None)

        embeds = self.format_log_embeds(entries,
                                        avatar_url=self.bot.guild.icon_url)

        if not embeds:
            embed = discord.Embed(
                color=discord.Color.red(),
                description="Aucun ticket n'a été trouvée pour cette requête."
                )
            return await ctx.send(embed=embed)

        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @logs.command(name='search')
    @checks.has_permissions(manage_messages=True)
    async def search(self, ctx, limit: Optional[int] = None, *, query):
        """Recherche dans tous les tickets un message contenant votre requête."""

        await ctx.trigger_typing()

        if not self.bot.self_hosted:
            embed = discord.Embed(
                color=discord.Color.red(),
                description='Cette commande ne fonctionne '
                            'que si vous auto-hébergez vos logs.'
                )
            return await ctx.send(embed=embed)

        query = {
            'guild_id': str(self.bot.guild_id),
            'open': False,
            '$text': {
                '$search': f'"{query}"'
                }
        }

        projection = {
            'messages': {'$slice': 5}
        }

        entries = await self.bot.db.logs.find(query, projection).to_list(limit)

        embeds = self.format_log_embeds(entries,
                                        avatar_url=self.bot.guild.icon_url)

        if not embeds:
            embed = discord.Embed(
                color=discord.Color.red(),
                description="Aucun ticket n'a été trouvée pour cette requête."
                )
            return await ctx.send(embed=embed)

        session = PaginatorSession(ctx, *embeds)
        await session.run()

    @commands.command()
    @checks.thread_only()
    async def reply(self, ctx, *, msg=''):
        """Répondre aux utilisateurs en utilisant cette commande.

        Prend en charge les pièces jointes et les images
        ainsi que l'intégration automatique des URLs d'image.
        """
        ctx.message.content = msg
        async with ctx.typing():
            await ctx.thread.reply(ctx.message)

    @commands.command()
    @checks.thread_only()
    async def anonreply(self, ctx, *, msg=''):
        """Répondre anonymement à un ticket.

        Vous pouvez modifier le nom, l'avatar et le tag de 
        l'utilisateur anonyme à l'aide de la commande config.

        Editez les variables de configuration `anon_username`,
        `anon_avatar_url` et `anon_tag` pour le faire.
        """
        ctx.message.content = msg
        async with ctx.typing():
            await ctx.thread.reply(ctx.message, anonymous=True)

    @commands.command()
    @checks.thread_only()
    async def note(self, ctx, *, msg=''):
        """Prenez une note sur le ticket actuel, utile pour noter le contexte."""
        ctx.message.content = msg
        async with ctx.typing():
            await ctx.thread.note(ctx.message)

    @commands.command()
    @checks.thread_only()
    async def edit(self, ctx, message_id: Optional[int] = None,
                   *, new_message):
        """Modifier un message envoyé à l'aide de la commande reply.

        Si `message_id` n'est pas fourni, ce sera
        le dernier message envoyé qui sera édité.

        `[message_id]` l'ID du message que vous souhaitez modifier.
        `new_message` est le nouveau message qui sera édité.
        """
        thread = ctx.thread

        linked_message_id = None

        async for msg in ctx.channel.history():
            if message_id is None and msg.embeds:
                embed = msg.embeds[0]
                if isinstance(self.bot.mod_color, discord.Color):
                    mod_color = self.bot.mod_color.value
                else:
                    mod_color = self.bot.mod_color
                if embed.color.value != mod_color or not embed.author.url:
                    continue
                # TODO: use regex to find the linked message id
                linked_message_id = str(embed.author.url).split('/')[-1]
                break
            elif message_id and msg.id == message_id:
                url = msg.embeds[0].author.url
                linked_message_id = str(url).split('/')[-1]
                break

        if not linked_message_id:
            raise commands.UserInputError

        await asyncio.gather(
            thread.edit_message(linked_message_id, new_message),
            self.bot.api.edit_message(linked_message_id, new_message)
        )

        await ctx.message.add_reaction('✅')

    @commands.command()
    @trigger_typing
    @checks.has_permissions(manage_messages=True)
    async def contact(self, ctx,
                      category: Optional[discord.CategoryChannel] = None, *,
                      user: Union[discord.Member, discord.User]):
        """Créez un ticket avec un membre spécifié.

        Si l'argument de catégorie facultatif est passé,
        le fil sera créé dans la catégorie spécifiée.
        """

        if user.bot:
            embed = discord.Embed(
                color=discord.Color.red(),
                description='Impossible de démarrer un ticket avec un bot.'
            )
            return await ctx.send(embed=embed)

        exists = await self.bot.threads.find(recipient=user)
        if exists:
            embed = discord.Embed(
                color=discord.Color.red(),
                description='Un ticket pour cet utilisateur '
                            f'existe déjà dans {exists.channel.mention}.'
            )

        else:
            thread = self.bot.threads.create(user, creator=ctx.author,
                                             category=category)
            await thread.wait_until_ready()
            embed = discord.Embed(
                title='Ticket créé',
                description=f'Discussion commencée dans {thread.channel.mention} '
                f'pour {user.mention}.',
                color=self.bot.main_color
            )

        await ctx.send(embed=embed)

    @commands.command()
    @trigger_typing
    @checks.has_permissions(kick_members=True)
    async def blocked(self, ctx):
        """Renvoie la liste d'utilisateurs bloqués"""
        embed = discord.Embed(title='Utilisateurs bloqués',
                              color=self.bot.main_color,
                              description='Voici une liste des utilisateurs bloqués.')

        users = []
        not_reachable = []

        for id_, reason in self.bot.blocked_users.items():
            user = self.bot.get_user(int(id_))
            if user:
                users.append((user, reason))
            else:
                not_reachable.append((id_, reason))

        if users:
            val = '\n'.join(u.mention + (f' - `{r}`' if r else '')
                            for u, r in users)
            embed.add_field(name='Actuellement connu', value=val)
        if not_reachable:
            val = '\n'.join(f'`{i}`' + (f' - `{r}`' if r else '')
                            for i, r in not_reachable)
            embed.add_field(name='Inconnu', value=val, inline=False)

        if not users and not not_reachable:
            embed.description = "Il n'y a actuellement aucun utilisateur bloqué."

        await ctx.send(embed=embed)

    @commands.command()
    @trigger_typing
    @checks.has_permissions(kick_members=True)
    async def block(self, ctx, user: Optional[User] = None, *,
                    after: UserFriendlyTime = None):
        """
        Empêcher un utilisateur d'utiliser les tickets support.

        Note: Les raisons commençant par "Message système:" 
        sont réservées à un usage interne.
        """
        reason = ''

        if user is None:
            thread = ctx.thread
            if thread:
                user = thread.recipient
            else:
                raise commands.UserInputError

        if after is not None:
            reason = after.arg
            if reason.startswith('Message système: '):
                raise commands.UserInputError
            elif re.search(r'%(.+?)%$', reason) is not None:
                raise commands.UserInputError
            elif after.dt > after.now:
                reason = f'{reason} %{after.dt.isoformat()}%'

        if not reason:
            reason = None

        mention = user.mention if hasattr(user, 'mention') else f'`{user.id}`'

        extend = f' for `{reason}`' if reason is not None else ''
        msg = self.bot.blocked_users.get(str(user.id))
        if msg is None:
            msg = ''

        if str(user.id) not in self.bot.blocked_users or extend or msg.startswith('Message système: '):
            if str(user.id) in self.bot.blocked_users:

                old_reason = msg.strip().rstrip('.') or 'sans raison'
                embed = discord.Embed(
                    title='Success',
                    description=f'{mention} a été précédemment bloqué pour '
                    f'"{old_reason}". {mention} est maintenant bloqué{extend}.',
                    color=self.bot.main_color
                )
            else:
                embed = discord.Embed(
                    title='Succès',
                    color=self.bot.main_color,
                    description=f'{mention} est maintenant bloqué{extend}.'
                )
            self.bot.config.blocked[str(user.id)] = reason
            await self.bot.config.update()
        else:
            embed = discord.Embed(
                title='Erreur',
                color=discord.Color.red(),
                description=f'{mention} est déjà bloqué.'
            )

        return await ctx.send(embed=embed)

    @commands.command()
    @trigger_typing
    @checks.has_permissions(kick_members=True)
    async def unblock(self, ctx, *, user: User = None):
        """
        Débloque un utilisateur des tickets support.

        Note: les motifs commençant par "Message système:" 
        sont réservés à un usage interne.
        """

        if user is None:
            thread = ctx.thread
            if thread:
                user = thread.recipient
            else:
                raise commands.UserInputError

        mention = user.mention if hasattr(user, 'mention') else f'`{user.id}`'

        if str(user.id) in self.bot.blocked_users:
            msg = self.bot.blocked_users.get(str(user.id))
            if msg is None:
                msg = ''
            del self.bot.config.blocked[str(user.id)]
            await self.bot.config.update()

            if msg.startswith('Message système: '):
                # If the user is blocked internally (for example: below minimum account age)
                # Show an extended message stating the original internal message
                reason = msg[16:].strip().rstrip('.') or 'sans raison'
                embed = discord.Embed(
                    title='Succès',
                    description=f'{mention} a été précédemment bloqué en interne en raison de '
                    f'"{reason}". {mention} est plus bloqué.',
                    color=self.bot.main_color
                )
            else:
                embed = discord.Embed(
                    title='Succès',
                    color=self.bot.main_color,
                    description=f'{mention} est plus bloqué.'
                )
        else:
            embed = discord.Embed(
                title='Erreur',
                description=f'{mention} est pas bloqué.',
                color=discord.Color.red()
            )

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Modmail(bot))
