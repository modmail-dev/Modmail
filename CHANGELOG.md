# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


# v2.10.0

### Added
- `anonreply` command to anonymously reply to the recipient. 
The username of the anonymous user defaults to the `mod_tag` (the footer text of a mod reply). The avatar defaults the guild icon url. However you can change both of these via the `anon_username`, `anon_avatar_url` and `anon_tag` config variables. 

### Changed
Your bot now logs all messages sent in a thread channel, including discussions that take place. You can now toggle to view them in the log viewer app.

# v2.9.4
Fixed a small bug due to a typo.

# v2.9.3
Forgot to enable custom embed colors.

### Added
- Ability to set a custom `mod_tag` (the text in the footer of the mod reply embed, which by default says "Moderator")

# v2.9.2

### Changed
- Improve format of thread info embed. Slightly cleaner and simpler now.
- All commands are now blurple instead of green.

### Fixed
- Bug where the close command wouldn't work if you didnt configure a log channel. 

### Added
- Ability to set your own custom `mod_color` and `recipient_color` for the thread message embeds.

# v2.9.1
Changed order of arguments for the contact command. This is so that you can use aliases to their full potential. 
For example: 
- `contact "Recruitment Category" @somedude` 

You can add an alias by doing: `alias add recruit contact "Recruitment Category"`

Now you can use the alias via: `recruit @somedude`

# v2.9.0

### Added
- New command `note` will add a system message to your thread logs. This is useful for noting the context of a conversation.

# v2.8.1

### Fixed
- Fixed bug where thread logs were getting duplicated when using the `contact` command.
- Fixed bug where the wrong key was used for logs which caused some `log` command log links to point to an HTTP 404 Not Found.
  - A minor oversight from commit 1ba74d9.

# v2.8.0

### Changed
- Major improvement in viewing thread logs.
- Log links are now rendered in HTML instead of plain text.

# v2.7.2

### Added 
- `config options` command to see a list of valid config variables that you can modify.

### Security
Thread channels will now default to being private (`@everyone`'s read message perms set to `false`).
  - If the thread creation category could not be resolved.
  - This will save you from some trouble if for whatever reason your configuration gets messed up.

# v2.7.1

### Changed

- All reference to "modmail" / "Mod Mail" / "ModMail" are changed to "Modmail".
- `log_channel_id` is now part of the config upon `setup`.
- Added the ability to set where threads are created using the `main_category_id` configuration option.

### Important Note

- If your Modmail bot was set up a long time ago, you may experience an issue where messages were sent outside of the category.
  - To fix this, set `main_category_id` to the ID of the Modmail category.
  
# v2.7.0

### Changed

- `move` command now syncs thread channel permissions with the category that it was moved to.
- `contact` command now supports an optional category argument (where the thread channel will be created).

# v2.6.3

Fixed small issue with finding thread.

# v2.6.2

Fixed log URLs for self-hosting users.
(This shouldn't affect anyone.)

# v2.6.1

### Fixed
- Replaced the testing `API_BASE_URL` with the actual URL.

# v2.6.0

Mostly internal changes. Some are slightly breaking. Keep a lookout for broken features and report them on our server.

### Added
- `threads` is now a default alias to `logs`.

### Changed
- Log URLs are moved to their own collection.
- Log URLs are now `https://logs.modmail.tk/LOGKEY`, no more numbers before the log key.
- We still support the numbers so as to not break everyone's URLs so quickly but both work at the moment.
- This is a huge change to the backend logging and there might be migration errors. If so, please contact us at our [discord server](https://discord.gg/2fMbf2N)

# v2.5.2

Non breaking internal changes.
(This shouldn't affect anyone.)

# v2.5.0

Non breaking internal changes.
(This shouldn't affect anyone.)

### Background
Bots hosted by Heroku restart at least once every 27 hours.
During this period, local caches are deleted, which results in the inability to set the scheduled close time to longer than 24 hours. This update resolves this issue. 
 - [PR #135](https://github.com/kyb3r/modmail/pull/135)


### Changed
 - Created a new internal config var: `closures`.
 - Store closure details into `closures` when the scheduled time isn't "now".
   - Loaded upon bot restart.
   - Deleted when a thread is closed.
 - Use `call_later()` instead of `sleep()` for scheduling.

# v2.4.5

### Fixed
Fixed activity setting due to flawed logic in `config.get()` function.

# v2.4.4

### Fixed
Fixed a bug in activity command where it would fail to set the activity on bot restart if the activity type was `playing`.

# v2.4.3

This update shouldn't affect anyone.

### Changed
 - Moved self-hosted log viewer to a separate repo.

# v2.4.2

### Added
- Ability to set your own Twitch URL for `streaming` activity status.

# v2.4.1

### Fixed
- Small bug in `activity` command.

# v2.4.0

Breaking changes.

### Added
- Added the `activity` command for setting the activity
- [PR #131](https://github.com/kyb3r/modmail/pull/131#issue-244686818) this supports multiple activity types (`playing`, `watching`, `listening` and `streaming`).

### Removed
- Removed the deprecated `status` command.
- This also means you will have to reset your bot status with the `activity` command, as `status` command is removed.

# v2.3.0

### Added
- Ability to self-host logs.

### Changed
- Improved format for log channel embeds.
- Roles are now comma-separated in info embed.
- This only applies to separate server setups.

### Fixed
- Bug in subscribe command; it will now unsubscribe after a thread is closed.

# v2.2.0

### Added
- Notify command `notify [role]`.
    - Notify a given role or yourself to the next thread message received.
    - Once a thread message is received you will be pinged once only.

- Subscribe command `sub [role]` / `unsub [role]`.
    - Subscribes yourself or a given role to be notified when thread messages are received.
    - You will be pinged for every thread message received until you unsubscribe.

### Changed
- Slightly improved log channel message format.

# v2.1.1

### Fixed
- Small bug in `close` command.

# v2.1.0

### Added
- Ability to set a custom thread creation response message.
    - Via `config set thread_creation_response [message]`.

### Changed
- Improve logs command format.
- Improve thread log channel message to have more relevant info.
- Improve close command.
    - You now can close the thread after a delay and use a custom thread close message.
    - You also now have the ability to close a thread silently.

# v2.0.10

### Security
- Fix a bug where blocked users were still able to message modmail.

# v2.0.9

### Added
- Support for custom blocked emoji and sent emoji.
- Use the `config set blocked_emoji` or `sent_emoji` commands.

### Quick Fix
- Support multiple images and file attachments in one message.
- This is only possible on mobile so its good to handle it in code.

# v2.0.8

Improvements to commands and new config options available.

### Added
- Added the ability to use your own log channel.
    - You can do this via the `config set log_channel_id <id>` command.
- Added the ability to use your own main inbox category.
    - You can do this via the `config set main_category_id <id>` command.

### Changed
- You now have the ability to supply a reason when blocking a user.
- Blocked users are now stored in the database instead of in the channel topic.
    - This means you can delete the top channel in the modmail category now. (Migrate first though.)

# v2.0.7

New command and improvements in bot update message interfaces.

### Added
- Added a `changelog` command to view the bot's changelog within discord.

### Changed
- `update` command now shows the latest changes directly from the [CHANGELOG.md](https://modmail.tk/) in the repo.
- Auto update messages also show the latest changes from the GitHub repo.
- Removed "latest changes" section from the `about` command.

# v2.0.6

### Fixed
- Fix logs sending duplicated thread close logs.
- The bot will now tell you that a user is no longer in the server when you try to reply to a thread.
    - Before this, it looked like you replied to the thread, but in reality, the message didn't get sent.

# v2.0.5

### Changed
- `alias` command now checks if you are adding a valid alias-command combo.
- Deleting a channel manually will now correctly close the thread and post logs.

# v2.0.4

### Fixed
- Fixed a one-off bug where the channel topic disappears, but modmail operations should still continue.
- Fixed `linked_message_id` issues.

# v2.0.3

Fixed some issues with how data is displayed in the info embed.

### Fixed
- Thread creation embed now shows the correct number of past logs.
- If using a separate server setup, roles in the info embed now are shown as names instead of mentions.
    - This is due to the fact that you can't mention roles across servers.

# v2.0.2

### Security
- Made the `logs` command require "manage messages" permissions to execute.
    - Before this patch, anyone could use the `logs` commands.

# v2.0.1

Bug fixes and minor improvements.

### Changed
- Improved `block`/`unblock` commands.
    - They now take a wider range of arguments: usernames, nicknames, mentions and user IDs.

### Fixed
- Setup command now configures permissions correctly so that the bot will always be able to see the main operations category.

# v2.0.0

This release introduces the use of our centralized [API service](https://github.com/kyb3r/webserver) to enable dynamic configuration, auto-updates, and thread logs.
To use this release you must acquire an API token from https://modmail.tk.
Read the updated installation guide [here](https://github.com/kyb3r/modmail/wiki/installation).

### Changed
- Stability improvements through synchronization primitives.
- Refactor thread management and code.
- Update command now uses `api.modmail.tk`.
- `contact` command no longer tells the user you messaged them 👻

### Fixed
- `status` command now changes playing status indefinitely.

### Added
- Dynamic `help` command (#84).
- Dynamic configuration through `api.modmail.tk`.
- Thread logs via `logs.modmail.tk` (#78).
    - `log` command added.
- Automatic updates (#73).
- Dynamic command aliases and snippets (#86).
- Optional support for using a separate guild as the operations center (#81).
- NSFW Command to change channels to NSFW (#77).

### Removed
- Removed `archive` command.
    - Explanation: With thread logs (that lasts forever), there's no point in archiving.
