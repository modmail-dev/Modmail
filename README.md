<div align="center">
    <img src='https://i.imgur.com/o558Qnq.png' align='center'>
    <br>
    <strong><i>A simple and functional modmail bot for Discord.</i></strong>
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

When a user sends a direct message to the bot, a channel is created within an isolated category. This channel is where messages will be relayed. To reply to a message, simply use the command `reply` in the channel. See a full list of commands [below](#features-and-commands).


## Installation

You have two options for using this bot, host on Heroku or self-host the bot. If you choose to install the bot using Heroku, you do not need to download anything. Read the **[installation guide](https://github.com/kyb3r/modmail/wiki/Installation)** or watch the **[video tutorial](https://youtu.be/TH_1QfKUl_k)**. If you have any problems join our [discord server](https://discord.gg/etJNHCQ) or just join anyways :wink:

## What is Heroku?

Heroku is a container based cloud platform that currently offers a free plan to host web apps. However, these apps have an ephemeral file system and thus cannot store any data on site. We have made Modmail be accessible to anyone while still being feature-rich, it's a community run project that lets anyone get it up and running 24/7 for free. So how does our bot store data? Config and logs are stored in a [centralised web service](https://modmail.tk) hosted by us. This enables you to get started easily and fast.

## Self-hosted logs

If you want complete control over your data and do not want to use the centralized API service, you can self host your logs. You can do this by adding two config variables: 

* `MONGO_URI` - MongoDB connection URI, you can get a free 500 MB cluster from [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
* `LOG_URL` - The URL of your log viewer Heroku app (`https://yourlogviewerappname.herokuapp.com`)

You also need to create a separate Heroku app for the log viewer that you can deploy from [here](https://github.com/kyb3r/logviewer).

## Features and Commands
The bot comes with a plethora of useful functionality. Take a look at the [list of commands](https://github.com/kyb3r/modmail/wiki/Features-and-commands).


### Automatic Updates
The bot checks for new updates every hour and automatically updates to a newer version if found. This bot is under active development so you can always look forward to new, useful features! If you do not want this functionality, for example, if you want to make changes to your fork, you can do so by adding a `disable_autoupdates` config variable. 

## Contributing
This project is licenced under MIT. If you have ideas for commands create an issue or pull request. Contributions are always welcome, whether it be documentation improvements or new functionality, please feel free to create a pull request.

If you use Modmail and love it, consider supporting me on [Patreon](https://www.patreon.com/kyber) :heart:
