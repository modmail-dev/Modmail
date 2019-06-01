<div align="center">
  <img src="https://i.imgur.com/o558Qnq.png" align="center">
  <br>
  <strong><i>A feature rich Modmail bot for Discord.</i></strong>
  <br>
  <br>
    
  <a href="https://heroku.com/deploy?template=https://github.com/kyb3r/modmail">
    <img src="https://img.shields.io/badge/deploy_to-heroku-997FBC.svg?style=for-the-badge">
  </a>
  <a href="https://github.com/kyb3r/modmail/">	
    <img src="https://api.modmail.tk/badges/instances.svg" alt="Bot instances">	
  </a>
  <a href="https://discord.gg/j5e9p8w">
    <img src="https://img.shields.io/discord/515071617815019520.svg?style=for-the-badge&colorB=7289DA" alt="Support">
  </a>
  
  <a href="https://patreon.com/kyber">
    <img src="https://img.shields.io/badge/patreon-donate-orange.svg?style=for-the-badge" alt="Python 3.7">
  </a>
  
  <a href="https://github.com/kyb3r/modmail/blob/master/LICENSE">
    <img src="https://img.shields.io/badge/license-mit-e74c3c.svg?style=for-the-badge" alt="MIT License">
  </a>

<br>
<img src='https://i.imgur.com/fru5Q07.png' align='center' width=500>
</div>


## What is Modmail?

Modmail is akin to Reddit's Modmail both in functionality and purpose. It serves as a shared inbox/feed for server staff to communicate with the userbase and vice versa in a seamless way that DMing a single person never could achieve.

While the core functionality is to get into contact with the server personal, it's extended  use includes but is not limited to organisational means. Feature or event requests, reporting other users and a comment/feedback/suggestion  box under the guise of anonymity because Modmail threads aren't public.

## How does it work?
When a member sends a direct message to the bot, a channel or "thread" is created within an isolated category for that member. This channel is where messages will be relayed and where any available staff member can respond to that user.

## Features


* **Highly Customisable**
  * Bot activity, prefix, category, log channel, etc.
  * Fully customisable command permission system.
  * Interface elements (color, responses, reactions, etc.)
  * Snippets and *command aliases*
  * Minimum account/guild age in order to create a thread.
* **Thread logs**
  * When you close a thread, a [log link](https://logs.modmail.tk/example) is generated and posted to your log channel.
  * Rendered in styled HTML like Discord.
  * Optional login in via Discord to protect your logs.
  * See past logs of a user with `?logs`
  * Searchable by text queries using `?logs search`
* **Robust implementation**
  * Scheduled tasks in human time, e.g. `?close in 2 hours silently`.
  * Editing and deleting messages is synced on both ends.
  * Support for the full range of message content (mutliple images, files).
  * Paginated commands interfaces via reactions.
  
This list is ever growing thanks to active development and our exceptional contributors. See a full list of documented commands by using the `help` command.

## Installation

### Heroku
Currently, the easiest way to set up the bot is by using Heroku, a container-based cloud platform. Installation via Heroku is done in your web browser and keeps the bot online 24/7 for free (If you verify with a credit card). The [**installation guide**](https://github.com/kyb3r/modmail/wiki/Installation) will guide you through the entire installation process. If you run into any problems, join the [development server](https://discord.gg/etJNHCQ) for help and support. 

### Locally 
Installation locally for development reasons or otherwise is as follows, you will need `python 3.7`.

Clone the repo
```console
$ git clone https://github.com/kyb3r/modmail
$ cd modmail
```

Install dependancies
```console
$ pip install -r requirements.txt
```

Rename the `config.json.example` to `config.json` and fill out the fields. 
And finally, run the bot.
```console
$ python3 bot.py
```

## Plugins

Modmail supports the use of third party plugins to extend or add functionality to the bot. This allows the introduction of niche features as well as anything else outside of the scope of the core functionality of Modmail. A list of third party plugins can be found using the `plugins registry` command. To develop your own, check out the [documentation](https://github.com/kyb3r/modmail/wiki/Plugins) for plugins.

## Contributing

Contributions to Modmail are always welcome, whether it be improvements to the documentation or new functionality, please feel free make the change. Check out our contribution [guidelines](https://github.com/kyb3r/modmail/blob/master/CONTRIBUTING.md) before you get started. 

This bot is free for everyone and always will be. If you like this project and would like to show your appreciation, here's the link for our **[Patreon](https://www.patreon.com/kyber)**. 
