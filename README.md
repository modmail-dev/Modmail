# Mod Mail for Discord
This is an open source discord bot made by kyb3r and improved upon suggestions by the users!

## Hosting on Heroku
### What is Heroku?
Heroku is a free hosting site that can host many web apps. However, the web apps cannot store any data.    
We have made Mod Mail to do exactly that. It was made to be *stateless* and not store any data in json files or any other storage files.

### How do I do it? 
If you choose to install the bot using Heroku, you do not need to download anything. In fact, you can set it all up on a phone!    

### Heroku Account

You need to make a Heroku account. Make one at [Heroku's Website](https://heroku.com/) and then follow the steps below: 

### Setting it up

1. Create a Bot Application for Discord
2. Head over to the [applicatons page](https://discordapp.com/developers/applications/me).
3. Click “new application”. Give it a name, picture and description.
4. Click “Create Bot User” and click “Yes, Do It!” when the dialog pops up.
5. Copy down the bot token. This is what is used to login to your bot and will be used at Step 8, or 11 if you are setting up on your PC.

[*Here's a GIF to explain the first 5 steps*](https://i.imgur.com/Y2ouW7I.gif)

6. Click this button: [![Deploy](https://www.herokucdn.com/deploy/button.png)](https://heroku.com/deploy)
7. Input some random name for your app, the heroku app name is not important.
8. Input your bot token from step 5 into the `TOKEN` field.
7. Put the [ID of your Server](https://support.discordapp.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-) into the `GUILD_ID` field.
10. Put the command prefix you want in the `PREFIX` field. e.g `?` The default prefix is `m.`
11. Click the `deploy app` button and wait for it to finish.
12. Click `manage app` and go into the `resources` tab. 
13. Now turn on the worker by clicking the pencil icon.
14. If you want, you can go over and check the application logs to see if everything is running smoothly.
15. Once the bot is online in your server, do `[your prefix]setup` and you are good to go!    
You can add the bot to your server with [this tool](https://finitereality.github.io/permissions-calculator/?v=0). Your Client ID is retrived from the [applicatons page](https://discordapp.com/developers/applications/me)

Now you should be done. Go over to discord and try it out!

Make sure to give the bot manage channel permissions!

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

## Updating your ModMail (Heroku)
1. Go to `https://github.com/<YOUR GITHUB USERNAME>/modmail/compare/master...kyb3r:master?quick_pull=1&title=Updating`
2. Click `Create pull request`    
![image representation](https://i.imgur.com/iMpMxWF.png)    
*It should look exactly like the image*
3. Scroll all the way down till you see the following image    
![this](https://i.imgur.com/UbODNga.png)
4. Click `Merge pull request`
5. Go back to Heroku and click `Deploy`
6. Click `Deploy Branch`

**Create an issue if you need help**

#### IF STEP ONE GIVES A 404 ERROR
You would have to redo from step 6 of [this](https://github.com/kyb3r/modmail/#setting-it-up)

## Thanks For Using This Bot!

If you do use the bot, a star on this repository is appreciated ;)

Dont copy this code or incorporate the code into your own bot without permission and/or credit.
