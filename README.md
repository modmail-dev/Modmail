<div align="center">
    <img src='https://i.imgur.com/o558Qnq.png' align='center'>
    <br>
    <strong><i>A simple and functional Modmail bot for Discord.</i></strong>
    <br>
    <br>


<a href="https://heroku.com/deploy?template=https://github.com/kyb3r/modmail">
    <img src="https://img.shields.io/badge/deploy_to-heroku-997FBC.svg?style=for-the-badge" />
</a>


<a href="https://discord.gg/j5e9p8w">
    <img src="https://img.shields.io/discord/515071617815019520.svg?style=for-the-badge&colorB=7289DA" alt="Support" />
</a>



<a href="https://github.com/kyb3r/modmail/">
    <img src="https://api.modmail.tk/badges/instances.svg" alt="Bot instances" />
</a>


<a href="https://patreon.com/kyber">
  <img src="https://img.shields.io/badge/patreon-donate-orange.svg?style=for-the-badge" alt="Python 3.7" />
</a>


<a href="https://github.com/kyb3r/modmail/blob/master/LICENSE">
  <img src="https://img.shields.io/badge/license-mit-e74c3c.svg?style=for-the-badge" alt="MIT License" />
</a>

</div>
<br>

## How does it work?


<img src='https://i.imgur.com/GGukNDs.png' align='right' height=300>

When a user sends a direct message to the bot, a channel is created within an isolated category. This channel is where messages will be relayed. To reply to the message, simply use the command `reply` in the channel. See a full list of commands in the [wiki](https://github.com/kyb3r/modmail/wiki).


## Installation

Currently the easiest and fastest way to set up the bot is using Heroku which is a service that offers a free plan for hosting applications. If you choose to install the bot using Heroku, you will not need to download anything. Read the **[installation guide](https://github.com/kyb3r/modmail/wiki/Installation)**. If you ran into any problems, join our [discord server](https://discord.gg/etJNHCQ) for help and support. Even if you don't have any issues, you should come and check out our awesome Discord community! :wink:

## Notable Features


### Customizability
There is a range of config variables you can dynamically change with the `config` command to change the appearance of the bot. For example embed color, responses, reactions, status etc. Snippets and custom command aliases are also supported, snippets are shortcuts for predefined messages that you can send. Add and remove snippets with the `snippets` command. The list of things you can change is ever growing thanks to the community for code contributions.

### Linked Messages
<img src='https://i.imgur.com/6L9aaNw.png' height=300 align='right'></img>

Did you accidentally send something you didn't mean to with the `reply` command? Don't fret, if you delete the original message on your side, this bot automatically deletes the corresponding message that was sent to the recipient of the thread!  This also works when you use the `edit` command to edit a message you have sent.

### Thread Logs

Thread conversations are automatically logged and a log link is provided with each thread. Logs are rendered with HTML and are presented in an aesthetically pleasing way, exactly like on discord, this especially integrates seamlessly with the mobile version of discord. Here's a link to an [example](https://logs.modmail.tk/02032d65a6f3).

### Automatic Updates
The bot checks for new updates every hour and automatically updates to a newer version if found. This bot is under active development so you can always look forward to new, useful features! If you do not want this functionality, for example, if you want to make changes to your fork, you can do so by adding a `disable_autoupdates` config variable. 

## Contributing
This project is licenced under MIT. If you have ideas for commands create an issue or pull request. Contributions are always welcome, whether it be documentation improvements or new functionality, please feel free to create a pull request.

If you use Modmail and love it, consider supporting me on **[Patreon](https://www.patreon.com/kyber)** :heart:
