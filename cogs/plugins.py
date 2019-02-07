import importlib
import os
import shutil
import stat
import subprocess

from colorama import Fore, Style
from discord.ext import commands

from core.models import Bot


class DownloadError(Exception):
    pass


class Plugins:
    """Plugins expand Mod Mail functionality by allowing third-party addons.

    These addons could have a range of features from moderation to simply
    making your life as a moderator easier!
    Learn how to create a plugin yourself here:
    https://github.com/kyb3r/modmail/wiki/Plugins
    """
    def __init__(self, bot: Bot):
        self.bot = bot
        self.bot.loop.create_task(self.download_initial_plugins())

    def _asubprocess_run(self, cmd):
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
                print(Fore.RED + msg + Style.RESET_ALL)
            else:
                try:
                    await self.load_plugin(*parsed_plugin)
                except DownloadError as exc:
                    msg = f'{parsed_plugin[0]}/{parsed_plugin[1]} - {exc}'
                    print(Fore.RED + msg + Style.RESET_ALL)

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
            error = exc.stderr.decode('utf-8').strip()
            if not error.endswith('already exists and is '
                                  'not an empty directory.'):
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
                error = exc.stderr.decode('utf8').strip()
                if error:
                    raise DownloadError(
                        f'Unable to download requirements: ```\n{error}\n```'
                    ) from exc

        try:
            self.bot.load_extension(ext)
        except ModuleNotFoundError as exc:
            raise DownloadError('Invalid plugin structure') from exc
        else:
            msg = f'Loaded plugins.{username}-{repo}.{plugin_name}'
            print(Fore.LIGHTCYAN_EX + msg + Style.RESET_ALL)

    @commands.group(aliases=['plugins'])
    @commands.is_owner()
    async def plugin(self, ctx):
        """Plugin handler. Controls the plugins in the bot."""
        if ctx.invoked_subcommand is None:
            cmd = self.bot.get_command('help')
            await ctx.invoke(cmd, command='plugin')

    @plugin.command()
    async def add(self, ctx, *, plugin_name):
        """Adds a plugin"""
        if plugin_name in self.bot.config.plugins:
            return await ctx.send('Plugin already installed')
        if plugin_name in self.bot.cogs.keys():
            # another class with the same name
            return await ctx.send('Another cog exists with the same name')

        message = await ctx.send('Downloading plugin...')
        async with ctx.typing():
            if len(plugin_name.split('/')) >= 3:
                parsed_plugin = self.parse_plugin(plugin_name)

                try:
                    await self.download_plugin_repo(*parsed_plugin[:-1])
                except DownloadError as exc:
                    return await ctx.send(
                        f'Unable to fetch plugin from Github: {exc}'
                    )

                importlib.invalidate_caches()
                try:
                    await self.load_plugin(*parsed_plugin)
                except DownloadError as exc:
                    return await ctx.send(f'Unable to load plugin: `{exc}`')

                # if it makes it here, it has passed all checks and should
                # be entered into the config

                self.bot.config.plugins.append(plugin_name)
                await self.bot.config.update()

                await message.edit(content='Plugin installed. Any plugin that '
                                   'you install is of your OWN RISK.')
            else:
                await message.edit(content='Invalid plugin name format. '
                                   'Use username/repo/plugin.')

    @plugin.command()
    async def remove(self, ctx, *, plugin_name):
        """Removes a certain plugin"""
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
                print(exc)
                self.bot.config.plugins.append(plugin_name)
                raise exc

            await self.bot.config.update()
            await ctx.send('Plugin uninstalled and '
                           'all related data is erased.')
        else:
            await ctx.send('Plugin not installed.')

    @plugin.command()
    async def update(self, ctx, *, plugin_name):
        """Updates a certain plugin"""
        if plugin_name not in self.bot.config.plugins:
            return await ctx.send('Plugin not installed')

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
                error = exc.stderr.decode('utf8').strip()
                await ctx.send(f'Error while updating: {error}')
            else:
                output = cmd.stdout.decode('utf8').strip()
                await ctx.send(f'```\n{output}\n```')

                if output != 'Already up to date.':
                    # repo was updated locally, now perform the cog reload
                    ext = f'plugins.{username}-{repo}.{name}.{name}'
                    importlib.reload(importlib.import_module(ext))

                    try:
                        await self.load_plugin(username, repo, name)
                    except DownloadError as exc:
                        await ctx.send(f'Unable to start plugin: `{exc}`')

    @plugin.command(name='list')
    async def list_(self, ctx):
        """Shows a list of currently enabled plugins"""
        if self.bot.config.plugins:
            msg = '```\n' + '\n'.join(self.bot.config.plugins) + '\n```'
            await ctx.send(msg)
        else:
            await ctx.send('No plugins installed')


def setup(bot):
    bot.add_cog(Plugins(bot))
