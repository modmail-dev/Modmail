# Mod Mail for Discord
This is an open source discord bot made by verixx and improved upon suggestions by the users!

## Hosting on Heroku
### What is Heroku?
Heroku is a free hosting site that can host many web apps. However, the web apps cannot store any data.    
We have made Mod Mail to do exactly that. It was made to be *stateless* and not store any data in json files or any other storage files.

### How do I do it? 
If you choose to install the bot using Heroku, you do not need to download anything. In fact, you can set it all up on a phone!    
*Provided you have your Server ID*

### GitHub Account

For this to work you will need to make a Github account (If you don't have one already). After you have made your Github account go to [this repository and fork it](https://github.com/verixx/modmail/fork).

### Heroku Account

After making a Github account, you need to make a Heroku account. Make one at [Heroku's Website](https://heroku.com/) and then follow the steps below: 

[![Heroku Tutorial](https://img.youtube.com/vi/MSJWMhC5X3I/0.jpg)](https://www.youtube.com/watch?v=MSJWMhC5X3I)

### Setting it up

1. Create a Bot Application for Discord
2. Head over to the [applicatons page](https://discordapp.com/developers/applications/me).
3. Click “new application”. Give it a name, picture and description.
4. Click “Create Bot User” and click “Yes, Do It!” when the dialog pops up.
5. Copy down the bot token. This is what is used to login to your bot and will be used at Step 8, or 11 if you are setting up on your PC.

*Here's a GIF to explain the first 5 steps*
![GIF to explain the first 5 steps](https://i.imgur.com/Y2ouW7I.gif)

6. Create anapplication on Heroku (this is pretty straightforward)
7. Go to your application settings and find the `config vars` section. 
8. Create a config variable, name the key to be `TOKEN` and the value to be your bot token as retrived from step 5.
9. Create another config variable, name the key to be `GUILD_ID` and the value to be the [ID of your Server](https://support.discordapp.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-).
9. Create yet another config variable, name the key to be `PREFIX` and the value to be the bot prefix you want.
10. Find the `deploy` section on your applications dashboard.
11. In deploy method, click on the GitHub option and link your Github account to Heroku.
12. Now select the forked repository and click `deploy application`
13. Go to the `resources` tab and turn on the worker.
14. If you want, you can go over and check the application logs to see if everything is running smoothly.
15. Once the bot is online in your server, do `[your prefix]setup` and you are good to go!    
You can add the bot to your server with [this tool](https://finitereality.github.io/permissions-calculator/?v=0). Your Client ID is retrived from the [applicatons page](https://discordapp.com/developers/applications/me)

Now you should be done. Go over to discord and try it out!

## Self-Hosting on your own PC or VPS    
### Installing Python

This is a bot written in the python programming language. So if you don't already have python correctly installed, you must [install it](http://www.ics.uci.edu/~pattis/common/handouts/pythoneclipsejava/python.html).

### Installing the Bot

Now that you have python installed, you are good to go. Follow the steps below for a successful installation.

1. Look at [Steps 1 to 5 of Setting up on Heroku](https://github.com/verixx/modmail/blob/master/README.md#setting-it-up)
6. Download the bot from the [github page](https://github.com/verixx/modmail/archive/master.zip).
7. Extract the zip file to the desktop or wherever you want.
8. Open your terminal or cmd.
9. Navigate to the bot folder. i.e `cd desktop/modmail-master`
10. Install all the requirements: `pip install -r requirements.txt`
11. Run the bot with `python bot.py` or on mac or linux `python3.6 bot.py`
12. Enter your token and server ID in the wizard.
13. Once the bot is online in your server, do `[your prefix]setup` and you are good to go!    
You can add the bot to your server with [this tool](https://finitereality.github.io/permissions-calculator/?v=0). Your Client ID is retrived from the [applicatons page](https://discordapp.com/developers/applications/me)

## Commands
Parameters are either [] or <>.    
[] - Optional Parameters    
<> - Mandatory Parameters    
Do not include these while typing your command    
Include your prefix in front of every commmand

| Command | Description | Usage |
| ------------- | ------------- | ------------- |
| setup  | Sets up your server for Mod Mail `ADMINISTRATOR Required` | `setup [modrole]` |
| reply | Sends a message to the current thread  | `reply <message...>` |
| close | Closes the current thread and deletes the channel | `close` |
| disable | Closes all threads and disables modmail for the server. `ADMINISTRATOR Required` | `disable` |


If you do use the bot, a star on this repository is appreciated ;)
