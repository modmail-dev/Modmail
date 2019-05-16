import importlib
import logging
import os
import shutil
import site
import stat
import subprocess
import sys

from discord.ext import commands

from core.models import Bot
from core.utils import info, error

logger = logging.getLogger('Modmail')


class DownloadError(Exception):
    pass


class Plugins:
    """Les plugins étendent les fonctionnalités du bot.

    Apprenez à créer un plugin vous-même ici:
    https://github.com/kyb3r/modmail/wiki/Plugins
    """
    def __init__(self, bot: Bot):
        self.bot = bot
        self.bot.loop.create_task(self.download_initial_plugins())

    @staticmethod
    def _asubprocess_run(cmd):
        return subprocess.run(cmd, shell=True, check=True,
                              capture_output=True)

    @staticmethod
    def parse_plugin(name):
        # returns: (username, repo, plugin_name)
        try:
            result = name.split('/')
            result[2] = '/'.join(result[2:])
        except IndexError:
            return None
        return tuple(result)

    async def download_initial_plugins(self):
        await self.bot._connected.wait()
        for i in self.bot.config.plugins:
            parsed_plugin = self.parse_plugin(i)

            try:
                await self.download_plugin_repo(*parsed_plugin[:-1])
            except DownloadError as exc:
                msg = f'{parsed_plugin[0]}/{parsed_plugin[1]} - {exc}'
                logger.error(error(msg))
            else:
                try:
                    await self.load_plugin(*parsed_plugin)
                except DownloadError as exc:
                    msg = f'{parsed_plugin[0]}/{parsed_plugin[1]} - {exc}'
                    logger.error(error(msg))

    async def download_plugin_repo(self, username, repo):
        try:
            cmd = f'git clone https://github.com/{username}/{repo} '
            cmd += f'plugins/{username}-{repo} -q'
            await self.bot.loop.run_in_executor(
                None,
                self._asubprocess_run,
                cmd
            )
            # -q (quiet) so there's no terminal output unless there's an error
        except subprocess.CalledProcessError as exc:
            err = exc.stderr.decode('utf-8').strip()
            if not err.endswith('existe déjà et est '
                                'pas un répertoire vide.'):
                # don't raise error if the plugin folder exists
                raise DownloadError(error) from exc

    async def load_plugin(self, username, repo, plugin_name):
        ext = f'plugins.{username}-{repo}.{plugin_name}.{plugin_name}'
        dirname = f'plugins/{username}-{repo}/{plugin_name}'
        if 'requirements.txt' in os.listdir(dirname):
            # Install PIP requirements
            try:
                await self.bot.loop.run_in_executor(
                    None, self._asubprocess_run,
                    f'python3 -m pip install -U -r {dirname}/'
                    'requirements.txt --user -q -q'
                )
                # -q -q (quiet)
                # so there's no terminal output unless there's an error
            except subprocess.CalledProcessError as exc:
                err = exc.stderr.decode('utf8').strip()
                if err:
                    raise DownloadError(
                        f'Impossible de télécharger les exigences: ```\n{error}\n```'
                    ) from exc
            else:
                if not os.path.exists(site.USER_SITE):
                    os.makedirs(site.USER_SITE)

                sys.path.insert(0, site.USER_SITE)

        try:
            self.bot.load_extension(ext)
        except ModuleNotFoundError as exc:
            raise DownloadError('Structure de plugin invalide') from exc
        else:
            msg = f'Plugins chargés.{username}-{repo}.{plugin_name}'
            logger.info(info(msg))

    @commands.group(aliases=['plugins'])
    @commands.is_owner()
    async def plugin(self, ctx):
        """Gestionnaire de plugins. Contrôle les plugins dans le bot."""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command('help')
            await ctx.invoke(cmd, command='plugin')

    @plugin.command()
    async def add(self, ctx, *, plugin_name):
        """Ajoute un plugin"""
        if plugin_name in self.bot.config.plugins:
            return await ctx.send('Plugin déjà installé')
        if plugin_name in self.bot.cogs.keys():
            # another class with the same name
            return await ctx.send('Un autre rouage existe avec le même nom')

        message = await ctx.send('Téléchargement du plugin...')
        async with ctx.typing():
            if len(plugin_name.split('/')) >= 3:
                parsed_plugin = self.parse_plugin(plugin_name)

                try:
                    await self.download_plugin_repo(*parsed_plugin[:-1])
                except DownloadError as exc:
                    return await ctx.send(
                        f'Impossible d\'extraire le plugin de Github: {exc}'
                    )

                importlib.invalidate_caches()
                try:
                    await self.load_plugin(*parsed_plugin)
                except DownloadError as exc:
                    return await ctx.send(f'Impossible de charger le plugin: `{exc}`')

                # if it makes it here, it has passed all checks and should
                # be entered into the config

                self.bot.config.plugins.append(plugin_name)
                await self.bot.config.update()

                await message.edit(content='Plugin installé. Vous êtes responsable de '
                                   'tout plugin que vous installez.')
            else:
                await message.edit(content='Format de nom pour le plugin invalide. '
                                   'Utilisation username/repo/plugin.')

    @plugin.command()
    async def remove(self, ctx, *, plugin_name):
        """Supprime un certain plugin"""
        if plugin_name in self.bot.config.plugins:
            username, repo, name = self.parse_plugin(plugin_name)
            self.bot.unload_extension(
                f'plugins.{username}-{repo}.{name}.{name}'
            )

            self.bot.config.plugins.remove(plugin_name)

            try:
                if not any(i.startswith(f'{username}/{repo}')
                           for i in self.bot.config.plugins):
                    # if there are no more of such repos, delete the folder
                    def onerror(func, path, exc_info):
                        if not os.access(path, os.W_OK):
                            # Is the error an access error?
                            os.chmod(path, stat.S_IWUSR)
                            func(path)

                    shutil.rmtree(f'plugins/{username}-{repo}',
                                  onerror=onerror)
            except Exception as exc:
                logger.error(str(exc))
                self.bot.config.plugins.append(plugin_name)
                raise exc

            await self.bot.config.update()
            await ctx.send('Plugin désinstallé et '
                           'toutes les données associées sont effacées.')
        else:
            await ctx.send('Plugin non installé.')

    @plugin.command()
    async def update(self, ctx, *, plugin_name):
        """Met à jour un certain plugin"""
        if plugin_name not in self.bot.config.plugins:
            return await ctx.send('Plugin non installé')

        async with ctx.typing():
            username, repo, name = self.parse_plugin(plugin_name)
            try:
                cmd = f'cd plugins/{username}-{repo} && git pull'
                cmd = await self.bot.loop.run_in_executor(
                    None,
                    self._asubprocess_run,
                    cmd
                )
            except subprocess.CalledProcessError as exc:
                err = exc.stderr.decode('utf8').strip()
                await ctx.send(f'Erreur lors de la mise à jour: {err}')
            else:
                output = cmd.stdout.decode('utf8').strip()
                await ctx.send(f'```\n{output}\n```')

                if output != 'Déjà à jour.':
                    # repo was updated locally, now perform the cog reload
                    ext = f'plugins.{username}-{repo}.{name}.{name}'
                    importlib.reload(importlib.import_module(ext))

                    try:
                        await self.load_plugin(username, repo, name)
                    except DownloadError as exc:
                        await ctx.send(f'Impossible de démarrer le plugin: `{exc}`')

    @plugin.command(name='list')
    async def list_(self, ctx):
        """Affiche une liste des plugins actuellement activés"""
        if self.bot.config.plugins:
            msg = '```\n' + '\n'.join(self.bot.config.plugins) + '\n```'
            await ctx.send(msg)
        else:
            await ctx.send('Aucun plugin installé')


def setup(bot):
    bot.add_cog(Plugins(bot))
