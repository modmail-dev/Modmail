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

![a](https://i.imgur.com/BVvIfru.png)


## Hosting on Heroku
### What is Heroku?
Heroku is a free hosting site that can host many web apps. However, the web apps cannot store any data on site (changing files). We have made Mod Mail to do exactly that. It was made to be *stateless* and not store any data in json files or any other storage files.

### How do I do it? 
If you choose to install the bot using Heroku, you do not need to download anything. In fact, you can set it all up on a phone!    

### Heroku Account

You need to make a Heroku account. Make one at [Heroku's Website](https://heroku.com/) and then follow the steps below: 

### Creating a bot account

1. Create a Bot Application for Discord
2. Head over to the [applicatons page](https://discordapp.com/developers/applications/me).
3. Click “new application”. Give it a name, picture and description.
4. Click “Create Bot User” and click “Yes, Do It!” when the dialog pops up.
5. Copy down the bot token. This is what is used to login to your bot and will be used at Step 8, or 11 if you are setting up on your PC. [Here's a GIF to explain the first 5 steps](https://i.imgur.com/Y2ouW7I.gif)

### Deploying the bot
[![Deploy](https://www.herokucdn.com/deploy/button.png)](https://heroku.com/deploy)

1. Click the button above
2. Input a name of your choosing for your app, the heroku app name is not important.
3. Input your bot token into the `TOKEN` field.
4. Put the [ID of your Server](https://support.discordapp.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-) into the `GUILD_ID` field.
5. Put the command prefix you want in the `PREFIX` field. e.g `?` The default prefix is `m.`
6. Click the `deploy app` button and wait for it to finish.
7. Click `manage app` and go into the `resources` tab. 
8. Now turn on the worker by clicking the pencil icon.
9. If you want, you can go over and check the application logs to see if everything is running smoothly.
10. Once the bot is online in your server, do `[your prefix]setup` and you are good to go!    

You can add the bot to your server with [this tool](https://finitereality.github.io/permissions-calculator/?v=0). Your Client ID is retrived from the [applicatons page](https://discordapp.com/developers/applications/me)

Now you should be done. Go over to discord and try it out! If you have any issues, join the [discord server](https://kybr.tk/discord).

**Make sure to give the bot manage channel permissions!**

## Self-Hosting on your own PC or VPS    
### Installing Python

This is a bot written in the python programming language. So if you don't already have python correctly installed, you must [install it](http://www.ics.uci.edu/~pattis/common/handouts/pythoneclipsejava/python.html).

### Installing the Bot

Now that you have python installed, you are good to go. Follow the steps below for a successful installation.

1. Look at [Steps 1 to 5 of Setting up on Heroku](https://github.com/kyb3r/modmail/blob/master/README.md#setting-it-up)
6. Download the bot from the [github page](https://github.com/kyb3r/modmail/archive/master.zip).
7. Extract the zip file to the desktop or wherever you want.
8. Open your terminal or cmd.
9. Navigate to the bot folder. i.e `cd desktop/modmail-master`
10. Install all the requirements: `pip install -r requirements.txt`
11. Run the bot with `python bot.py` or on mac or linux `python3.6 bot.py`
12. Enter your token and server ID in the wizard.
13. Once the bot is online in your server, do `[your prefix]setup` and you are good to go!    
You can add the bot to your server with [this tool](https://finitereality.github.io/permissions-calculator/?v=0). Your Client ID is retrived from the [applicatons page](https://discordapp.com/developers/applications/me)

## Thanks For Using This Bot!

If you do use the bot, a star on this repository is appreciated ;)

This project is licenced under MIT.

## Contributing

Feel free to contribute to the development of this bot.
