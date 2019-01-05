<h1 align="center">Discord Mod Mail Bot</h1>

<div align="center">
    <strong><i>A simple and functional modmail bot.</i></strong>
    <br>
    <br>

<a href="">
  <img src="https://img.shields.io/badge/build-passing-7289DA.svg?style=for-the-badge" alt="Travis" />
</a>

<a href="">
  <img src="https://img.shields.io/badge/python-3.7-7289DA.svg?style=for-the-badge" alt="Travis" />
</a>

<a href="https://github.com/kyb3r/modmail/blob/master/LICENSE">
  <img src="https://img.shields.io/github/license/kyb3r/modmail.svg?style=for-the-badge&colorB=7289DA" alt="Travis" />
</a>

</div>
<br>
<div align="center">
    This is an open source discord bot made by kyb3r and improved upon suggestions by the users! It enables server members to DM it, the messages then get relayed to the server moderators who can then respond through the bot. In essence this bot serves as a means for members to easily communicate with server leadership in an organised manner.

</div>

## How does it work?


<img src='https://i.imgur.com/GGukNDs.png' align='right' height=300>

When a user sends a direct message to the bot, a channel is created within an isolated category. This channel is where messages will be relayed. To reply to a message, simply use the command `reply` in the channel. See a full list of commands [below](#commands).


## Installation

You have two options for using this bot, hosting on Heroku or self hosting the bot. If you choose to install the bot using Heroku, you do not need to download anything. Read the installation guide [here](https://github.com/kyb3r/modmail/wiki/Installation). If you have any problems join our discord server [here](https://discord.gg/etJNHCQ).

### What is Heroku?
Heroku is a free hosting site that can host many web apps. However, the web apps cannot store any data on site (changing files). We have made Mod Mail to do exactly that. It was made to be *stateless* and not store any data in any files, utilising discord channel topics for tracking and relaying conversations.

## Commands

### Modmail related 

| Name     | Command                                                    |
|----------|------------------------------------------------------------|
| setup    | Sets up a server for modmail                               |
| reply    | Reply to users using this command.                         |
| edit     | Edit a message that was sent using the reply command.      |
| contact  | Create a thread with a specified member.                   |
| close    | Close the current thread.                                  |
| move     | Moves the thread channel to a specified category           |
| logs     | Shows a list of previous modmail thread logs of a member.  |
| block    | Block a user from using modmail.                           |
| blocked  | Returns a list of blocked users                            |
| unblock  | Unblocks a user from using modmail.                        |
| nsfw     | Flags a modmail thread as nsfw.                            |
| snippets | Returns a list of snippets that are currently set.         |
| mention  | Changes what the bot mentions at the start of each thread. |

### Utility commands
| Name     | Command                                                    |
|----------|------------------------------------------------------------|
| help     | Shows the help message.                                    |
| update   | Checks for new versions and updates the bot                |
| github   | Shows the github user your modmail api token is linked to. |
| prefix   | Changes the prefix for the bot.                            |
| alias    | Returns a list of aliases that are currently set.          |
| about    | Shows information about the bot.                           |
| status   | Set a custom playing status for the bot.                   |
| ping     | Pong! Returns your websocket latency.                      |
| eval     | Evaluates python code (Bot owner only)                     |
| config   | Manually change configuration for the bot.                 |

## Features

### Snippets
Snippets are shortcuts for predefined messages that you can send. Add and remove snippets with the `snippets` command.

### Custom Mentions
If you want the bot to mention a specific role instead of `@here`, use the `mention` command.

### Delete Linked Messages
Did you accidentally send something you didnt mean to with the `reply` command? Dont fret, if you delete the original message on your side, this bot automatically deletes the corresponding message that was sent to the recipient of the thread! This also works with message edits in reverse.

### Thread Logs
Thread conversations are automatically logged and a log link (logs.modmail.tk) is provided with each thread.

### Automatic Updates
The bot checks for new updates every hour and automatically updates to a newer version if found. You can disable this functionality by adding a `disable_autoupdates` config variable.

## Contributing
This project is licenced under MIT. Feel free to contribute to the development of this bot.
