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

<h1 align="center"><a href="https://github.com/kyb3r/modmail/wiki/Installation">Installation</a></h1>

You have two options for using this bot, hosting on Heroku or self hosting the bot. If you choose to install the bot using Heroku, you do not need to download anything. In fact, you can set it all up on a phone! Read the installation guide [here](https://github.com/kyb3r/modmail/wiki/Installation).

### What is Heroku?
Heroku is a free hosting site that can host many web apps. However, the web apps cannot store any data on site (changing files). We have made Mod Mail to do exactly that. It was made to be *stateless* and not store any data in any files, utilising discord channel topics for tracking and relaying conversations.

### Updating
If you are keen to stay updated with the latest features then follow the updating guide [here](https://github.com/kyb3r/modmail/wiki/Updating). It has a few more steps so it may not be for everyone.

## Commands

| Name         | Description                                                          |
|--------------|----------------------------------------------------------------------|
| setup        | Sets up the categories that will be used by the bot.                 |
| contact      | Allows a moderator to initiate a thread with a given recipient.
| reply        | Sends a message to the current thread's recipient.                   |
| close        | Closes the current thread and deletes the channel.                   |
| archive      | Closes the thread and moves the channel to the archive category.     | 
| block        | Blocks a user from using modmail                                     |
| unblock      | Unblocks a user from using modmail                                   |
| snippets     | Shows a list of snippets that are currently configured.              |
| customstatus | Sets the bot playing status to a message of your choosin             |
| disable      | Closes all threads and disables modmail for the server.              |

## Features

### Snippets
Snippets are shortcuts for predefined messages that you can send. You can add snippets by adding config variables by prefixing the name of the snippet with `SNIPPET_` and setting the value to what you want the message to be. For example you can make a snippet called `hi` by making a config variabled named `SNIPPET_hi`, you can then use the snippet by typing the command `?hi` in the thread you want to reply to.

### Custom Mentions
If you want the bot to mention a specific role instead of `@here`, you need to set a config variable `MENTION` and set the value to the mention of the role or user you want mentioned. To get the mention of a role or user, type `\@role` in chat and you will see something like `<@&515651147516608512>` use this string as the value for the config variable.

### Delete Linked Messages
Did you accidentally send something you didnt mean to with the `reply` command? Dont fret, if you delete the original message on your side, this bot automatically deletes the corresponding message that was sent to the recipient of the thread! 

## Thanks For Using This Bot!

If you do use the bot, a star on this repository is appreciated! If you want to support me here is my [patreon](https://www.patreon.com/kyber). 

This project is licenced under MIT. Feel free to contribute to the development of this bot.
