<h1 align="center">Discord Mod Mail Bot</h1>

<div align="center">
    <strong><i>A simple and functional modmail bot.</i></strong>
    <br>
    <br>

<a href="https://travis-ci.com/kyb3r/dhooks">
  <img src="https://img.shields.io/badge/build-passing-7289DA.svg?style=for-the-badge" alt="Travis" />
</a>

<a href="https://pypi.org/project/dhooks/">
  <img src="https://img.shields.io/badge/python-3.6-7289DA.svg?style=for-the-badge" alt="Travis" />
</a>

<a href="https://github.com/kyb3r/modmail/blob/master/LICENSE">
  <img src="https://img.shields.io/github/license/kyb3r/modmail.svg?style=for-the-badge&colorB=7289DA" alt="Travis" />
</a>

</div>
<br>
<div align="center">
    This is an open source discord bot made by kyb3r and improved upon suggestions by the users! This bot enables server members to DM it, the messages then get relayed to the server moderators who can then respond through the bot. In essence this bot serves as a means for members to easily communicate with server leadership in an organised manner.

</div>

## How does it work?


<img src='https://i.imgur.com/aHtn4C5.png' align='right' height=140>

Assuming you got the bot setup (Read below on how to set it up), the first thing that you would do is type the command ```<prefix>setup [modrole]``` where `[modrole]` is an optional role you can specify which determines who can see the relayed messages. If a role is not specified, the bot will choose the first role that has `manage guild` permissions as the modrole. The bot will then set up a channel category named `Mod Mail`.

When a user sends a direct message to the bot, a channel is created within this new category. This channel is where messages will be relayed. To reply to a message, simply type the command `<prefix>reply <message>` in the channel.

## What it looks like

![a](https://i.imgur.com/LZCHeaR.jpg)

# [Installation]((https://github.com/kyb3r/modmail/wiki/Installation))

You have the two options of using this bot, hosting on Heroku or self hosting the bot. If you choose to install the bot using Heroku, you do not need to download anything. In fact, you can set it all up on a phone! Read the installation guide [here](https://github.com/kyb3r/modmail/wiki/Installation)

### What is Heroku?
Heroku is a free hosting site that can host many web apps. However, the web apps cannot store any data on site (changing files). We have made Mod Mail to do exactly that. It was made to be *stateless* and not store any data in any files, utilising discord channel topics for tracking and relaying conversations. 

## Thanks For Using This Bot!

If you do use the bot, a star on this repository is appreciated ;)
If you want to support me here is my [patreon](https://www.patreon.com/kyber). 

This project is licenced under MIT.

## Contributing

Feel free to contribute to the development of this bot.
