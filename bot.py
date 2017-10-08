'''
MIT License

Copyright (c) 2017 verixx

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

'''

import discord
from discord.ext import commands
import datetime

class Modmail(commands.Bot):
    def __init__(self, token):
        super().__init__(command_prefix='?')
        self.uptime = datetime.datetime.utcnow()
        self.add_commands()

    def add_commands(self):
        '''Adds commands automatically'''
        for attr in dir(self):
            cmd = getattr(self, attr)
            if isinstance(cmd, commands.Command):
                self.add_command(cmd)

    @property
    def token(self):
        '''Returns your token wherever it is'''
        with open('data/config.json') as f:
            config = json.load(f)
            if config.get('TOKEN') == "your_token_here":
                if not os.environ.get('TOKEN'):
                    self.run_wizard()
            else:
                token = config.get('TOKEN').strip('\"')
        return os.environ.get('TOKEN') or token

    @staticmethod
    def run_wizard():
        '''Wizard for first start'''
        print('------------------------------------------')
        token = input('Enter your token:\n> ')
        print('------------------------------------------')
        data = {
                "TOKEN" : token,
            }
        with open('data/config.json','w') as f:
            f.write(json.dumps(data, indent=4))
        print('------------------------------------------')
        print('Restarting...')
        print('------------------------------------------')
        os.execv(sys.executable, ['python'] + sys.argv)

    @classmethod
    def init(bot, token=None):
        '''Starts the actual bot'''
        selfbot = bot()
        safe_token = token or selfbot.token.strip('\"')
        try:
            selfbot.run(safe_token, bot=False, reconnect=True)
        except Exception as e:
            print(e)

    async def on_connect(self):
        print('---------------')
        print('Modmail connected!')

    async def on_ready(self):
        '''Bot startup, sets uptime.'''
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()
        print(textwrap.dedent(f'''
        ---------------
        Client is ready!
        ---------------
        Author: verixx#7220
        ---------------
        Logged in as: {self.user}
        User ID: {self.user.id}
        ---------------
        '''))

    @commands.command()
    async def setup(self, ctx):
        '''Sets up a server for modmail'''
        if discord.utils.get(ctx.guild.categories, name='modmail'):
            return await ctx.send('This server is already set up.')
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }

        modrole = self.guess_modrole(ctx)
        if modrole:
            overwrites[modrole] = discord.PermissionOverwrite(read_messages=True)

        await ctx.guild.create_category(name='modmail', overwrites=overwrites)
        await ctx.send('Successfully set up server.')

    def guess_modrole(ctx):
        '''
        Finds a role if it has the manage_guild 
        permission or if it startswith `mod`
        '''
        perm_check = lambda r: r.permissions.manage_guild
        loose_check = lambda r: r.name.lower.startswith('mod')
        perm = discord.utils.find(perm_check, ctx.guild.roles)
        loose = discord.utils.find(loose_check, ctx.guild.roles)
        return perm or loose

    async def process_modmail(self, message):
        pass

    async def on_message(self, message):
        self.process_commands(message)
        if message.channel.is_private:
            await self.process_modmail(message)

        
