# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

#v2.0.4

### Fixed
- Fixed a one off bug where the channel topic dissapears, but modmail operations should still continue
- Fixed linked_message_id issues.

# v2.0.3

Fixed some issues with how data is displayed in the info embed.

### Fixed
- Thread creation embed now shows the correct amount of past logs. 
- If using a seperate server setup, roles in the info embed now are shown as names instead of mentions.
    - This is due to the fact that you can't mention roles across servers.

# v2.0.2

### Security
- Made the logs command require manage messages permissions to execute. 
    - Before this patch, anyone could use the logs commands.

# v2.0.1

Bug fixes and minor improvements.

### Changed
- Improved block/unblock commands.
    - They now take a wider range of arguments: Usernames, nicknames, mentions and user IDs.

### Fixed
- Setup command now configures permissions correctly so that the bot will always be able to see the main operations category.

# v2.0.0

This release introduces the use of our centralized [API service](https://github.com/kyb3r/webserver) to enable dynamic configuration, auto-updates, and thread logs. To use this release you must acquire an API token from https://modmail.tk. Read the updated installation guide [here](https://github.com/kyb3r/modmail/wiki/installation).

### Changed
- Stability improvements through synchronization primitives 
- Refactor thread management and code
- Update command now uses `api.modmail.tk` 
- Removed `archive` command
    - Explanation: With thread logs (that lasts forever), there's no point in archiving.
- `contact` command no longer tells the user you messaged them 👻 

### Fixed
- Status command now changes playing status indefinitely

### Added
- Dynamic help command (#84)
- Dynamic configuration through `api.modmail.tk` 
- Thread logs via `logs.modmail.tk` (#78)
    - `log` command added
- Automatic updates (#73)
- Dynamic command aliases and snippets (#86)
- Optional support for using a seperate guild as the operations center (#81)
- NSFW Command to change channels to NSFW (#77)
