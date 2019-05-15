<div align="center">
  <img src="https://i.imgur.com/o558Qnq.png" align="center">
  <br>
  <strong><i>A simple and functional Modmail bot for Discord.</i></strong>
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
</div>


## How Does Modmail Work?

When a user sends a direct message to the bot, a channel is created within an isolated category. This channel is where messages will be relayed. To reply to the message, simply use the command `?reply` in the channel. A full list of commands can be found by using the `?help` command.

## Features

* Highly Customisable:
  * Bot activity, prefix, etc.
  * Command permissions
  * Interface elements (color, responses, reactions, etc.)
  * Snippets and *command aliases*
  * Minimum account/guild age in order to create a thread.
* Thread logs, e.g. https://logs.modmail.tk/example
  * When you close a thread, a log link is generated and posted to your log-channel.
  * Rendered in styled HTML like Discord.
  * Optional login in via Discord to protect your logs.
  * See past logs of a user with `?logs`
  * Searchable by text queries using `?logs search`
* Aesthetic command interfaces e.g Pagination via reactions
* Scheduled closing - e.g. `?close in 2 hours silently`
* Blocking users e.g. `?block @user spamming for 2 days`
* Get notified/subscribe for thread messages. (`?notify` and `?sub`)
* Linked thread messages Editing/deleting messages is synced on both ends.

* Optional automatic updates to stay up to date with the latest features.
  
This list is ever growing thanks to active development and our exceptional contributors.


## Installation

### Heroku
Currently, the easiest way to set up the bot is by using Heroku, a container-based cloud platform. Installation via Heroku is done in your web browser and keeps the bot online 24/7 for free. The [**installation guide**](https://github.com/kyb3r/modmail/wiki/Installation) will guide you through the entire installation process. If you run into any problems, join the [development server](https://discord.gg/etJNHCQ) for help and support. 

### Locally 
Installation locally for development reasons or otherwise is as follows, you will need `python 3.7` and `pipenv`.

Clone the repo
```console
$ git clone https://github.com/kyb3r/modmail
$ cd modmail
```

Install dependancies
```console
$ pipenv install
```

Rename the `config.json.example` to `config.json` and fill out the fields. 
And finally, run the bot.
```console
$ pipenv run python3 bot.py
```

## Contributing

This project is licenced under MIT. If you have any new ideas, create an issue or a pull request. Contributions to Modmail are always welcome, whether it be improvements to the documentation or new functionality, please feel free make the change.

If you use Modmail and love it, consider becoming a patron on **[Patreon](https://www.patreon.com/kyber)** :smile:
