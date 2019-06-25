# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

# v3.0.0

### Added 

- Sponsors command that will list sponsors.
- An alert will now be sent to the log channel if a thread channel fails to create. This could be due to a variety of problems such as insufficient permissions or the category channel limit is met. 
- Threads will close automatically after some time when `thread_auto_close` is set.
- Custom closing message can be set with `thread_auto_close_response`.

### Breaking Changes

- Removed autoupdate functionality and the `update` command in favour of the [Pull app](https://github.com/apps/pull).

Read more about updating your bot [here](https://github.com/kyb3r/modmail/wiki/updating)

### Changed
- Channel names now can contain unicode characters.
- Debug logs are now located in a unique file for each bot. (Internal change) 
- Default cogs always appear first in the help command now.

### Fixed
- Editing notes now works, minor bug with edit command is fixed.
- Bug in the `oauth` command where the response message fails to send when an ID is provided.
- Plugin requirement installation now works in virtual environments


# v2.24.1

### Fixed

Fixed a bug with branches and `plugin update`.

# v2.24.0

### Added

Branch support for `plugin add` and in registry. Typically for developers.    

# v2.23.0

### Added 

Added a "Mutual servers" field to the genesis embed if:
a) The user is not in the main guild.
b) The user shares more than 1 server with the bot.

### Changed

Notes taken using the `?note` command are now automatically pinned within the thread channel.

# v2.22.0

### Added

Added a 🛑 reaction to the paginators to delete the embed.  

### Fixed

`?blocked` is now paginated using reactions. This fixes [#249](https://github.com/kyb3r/modmail/issues/249)

# v2.21.0

### Added 

New `?plugin registry compact` command which shows a more compact view of all plugins.

# v2.20.2

### Plugin Registry

Plugin developers can now make a PR to include their plugin in the `plugin registry` command.
Add your plugin in the `plugins/registry.json` file in the main repository.

### Changed

`?debug` command now shows the most recent logs first. (Starts at the last page)

# v2.20.1

### What's new?

  - New error message when using thread-only commands outside of threads.
  - `?unnotify`, ability to undo `?notify`.
  - `?notify` and `?subscribe` now accepts other users.

### Changes

This update contains mostly internal changes.
  - Implemented support for the new discord.py v1.1.1.
  - Improved help text for most commands.
  - Completely revamped help command, few user changes.
  - Removed abc (internal).

# v2.20.0

### What's new? 

New `oauth` whitelist command which allows you to whitelist users so they can log in via discord to view logs. To set up oauth login for your logviewer app check the logviewer [repo](https://github.com/kyb3r/logviewer).

# v2.19.1

### Changed

- Ability to force an update despite having the same version number. Helpful to keep up-to-date with the latest GitHub commit.
  - `?update force`.
- Plugin developers now have a new event called `on_plugin_ready`, this is coroutine is awaited when all plugins are loaded. Use `on_plugin_ready` instead of `on_ready` since `on_ready` will not get called in plugins.

# v2.19.0

### What's new?

- New config variable `guild_age`, similar to `account_age`, `guild_age` sets a limit as to how long a user has to wait after they joined the server to message Modmail.
- `guild_age` can be set the same way as `account_age`.

# v2.18.5

Fix help command bug when using external plugins.

# v2.18.4

Fix the teams permission bug.

# v2.18.2

### Changed

Commands now have better error messages, instead of just sending the help message for a command when an argument fails to be converted to its specified object, the bot now says things like "User 'bob' not found" instead.

# v2.18.1

Un-deprecated the `OWNERS` config variable to support discord developer team accounts.

# v2.18.0

### New Permissions System

- A brand new permission system! Replacing the old guild-based permissions (ie. manage channels, manage messages), the new system enables you to customize your desired permission level specific to a command or a group of commands for a role or user.
- There are five permission groups/levels:
  - Owner [5]
  - Administrator [4]
  - Moderator [3]
  - Supporter [2]
  - Regular [1]

### Usage 

You may add a role or user to a permission group through any of the following methods:
- `?permissions add level owner @role`
- `?permissions add level supporter member-name`
- `?permissions add level moderator everyone`
- `?permissions add level moderator @member#1234`
- `?permissions add level administrator 78912384930291853`

The same applies to individual commands permissions:
- `?permissions add command command-name @member#1234`
- ... and the other methods listed above.

To revoke permission, use `remove` instead of `add`.

To view all roles and users with permission for a permission group or command do:
-  `?permissions get command command-name`
-  `?permissions get level owner`

By default, all newly set up Modmail will have `OWNER` set to the owner of the bot, and `REGULAR` set to @everyone.

### Breaking

When updating to this version, all prior permission settings with guild-based permissions will be invalidated. You will need to convert to the above system.
`OWNERS` will also get removed, you will need to set owners through `?permissions add level owner 212931293123129` or any way listed above.

### New Command

- A `?delete` command, which is an alternative to manually deleting a message. This command is created to no longer require manage messages permission to recall thread messages.

### Changed

- The help message no longer conceals inaccessible commands due to check failures.

# v2.17.2

### Changed

- Logs search command will search through log keys as well now. 
- For example, `?logs search e7499e82f8ff`.

# v2.17.1
### What's new?

Stricter fallback genesis embed search.

### Changed
How modmail checks if a channel is a thread: 

1. First the bot checks if the channel topic is in the format `User ID: xxxx`, this means it is a thread.
2. If a channel topic is not found, the bot searches through message history of a channel to find the thread creation embed. This step should never yield a thread for a normal user, but in the case of a another bot messing up the channel topic (happened to a user before) this extra step was added. 


# v2.17.0

### What's new?

Added a config option `reply_without_command` which when present, enables the bot to forward any message sent in a thread channel to the recipient. (Replying without using a command)

To enable this functionality, do `?config set reply_without_command true` and to disable it, use `?config del reply_without_command`.


### Changed

The `move` command now only requires `manage_messages` perms instead of `manage_channels`

# v2.16.1

### Fixed

An issue where a scheduled close would not execute over a long period of time if the recipient no shares any servers with the bot.

# v2.16.0

### Changed

All support for Modmail API (api.modmail.tk) has terminated. 
If you're still using api.modmail.tk, you will need to migrate to the self-hosted database
option ASAP. Your bot will not work unless you switch to the self-hosted option. Refer to the 
installation tutorial for information regarding self-hosted Modmail.

If a member leaves/joins (again) while they are a recipient of a thread, a message will be sent to notify you that this has occured.

# v2.15.1

### Fixed

Emergency patch of a SyntaxError.

# v2.15.0

### What's new?

Added the ability to change the default close message via the introduction of two config variables.

- `thread_close_response` - when someone closes the thread.
- `thread_self_close_response` - when the recipient closes their own thread.

They will be provided by string variables that you can incorporate into them:

- `closer` - the user object that closed the thread.
- `logkey` - the key for the thread logs e.g. (`5219ccc82ad4`)
- `loglink` - the full link to the thread logs e.g. (`https://logwebsite.com/logs/5219ccc82ad4`)

Example usage would be: ``?config set thread_close_message {closer.mention} closed the thread, here is the link to your logs: [**`{logkey}`**]({loglink})``

# v2.14.0

### What's new?

Added the ability to enable the recipient to close their own threads. This takes place in the form of a reaction that the user can click to close their thread. This functionality is now enabled by default. 

To disable this, do `?config set disable_recipient_thread_close true`

### More Customisability!

More config variables have been added that you can edit.

- `close_emoji` - the emoji that the user can click on to close a thread. Defaults to a lock (🔒)

You now have complete control of the look of the thread creation and close embeds the users see.

- `thread_creation_title` - the title of the embed. Defaults to 'Thread Created'
- `thread_creation_footer` - the footer text in the embed. Defaults to 'Your message has been sent...'
- `thread_close_title` - the title of the embed. Defaults to 'Thread Closed'
- `thread_close_footer` - the footer text in the embed. Defaults to 'Replying will create a new thread'

# v2.13.13

### What's new? 

Added the ability to disable the `sent_emoji` and `blocked_emoji` when a user messages modmail.

You can do this via `?config set sent_emoji disable`

### Fixed

The bot now handles having too many roles to show in the thread created embed. 

# v2.13.12
### What's new?

Added image link in title in case discord fails to embed an image.

# v2.13.11

### What's new?
- Introduced a new configuration variable `account_age` for setting a minimum account creation age.
  - Users blocked by this reason will be stored in `blocked` along with other reasons for being blocked.
  - `account_age` needs to be an ISO-8601 Duration Format (examples: `P12DT3H` 12 days and 3 hours, `P3Y5M` 3 years and 5 months `PT4H14M999S` 4 hours 14 minutes and 999 seconds). https://en.wikipedia.org/wiki/ISO_8601#Durations.
  - You can set `account_age` using `config set account_age time` where "time" can be a simple human readable time string or an ISO-8601 Duration Format string.

### Changed
- `block` reason cannot start with `System Message: ` as it is now reserved for internal user blocking.
- `block`, like `close`, now support a block duration (temp blocking).

# v2.13.10

### Fixed
- Fixed an issue where status and activity does not work if they were modified wrongly in the database.
  - This was especially an issue for older Modmail users, as the old `status` configuration variable clashes with the new `status` variable.

# v2.13.9

### Fixed
- Fixed a bug where an error was raised when a message with received during a scheduled closure.

# v2.13.8

### Fixed
- A bug where a thread was blocked from sending messages when multiple images were uploaded, due to a typo.

### Changed
- Uses https://hasteb.in instead of https://hastebin.com for `?debug hastebin`.

# v2.13.7

### What's new?
- The ability to enable typing interactions. 
  - If you want the bot to type in the thread channel if the user is also typing, add the config variable `user_typing` and set it to "yes" or "true". use `config del` to disable the functionality. The same thing in reverse is also possible if you want the user to see the bot type when someone is typing in the thread channel add the `mod_typing` config variable.
- New `status` command, change the bot's status to `online`, `idle`, `dnd`, `invisible`, or `offline`.
  - To remove the status (change it back to default), use `status clear`.
  - This also introduces a new internal configuration variable: `status`. Possible values are `online`, `idle`, `dnd`, `invisible`, and `offline`.
  
### Changed
- The internals for `activity` has drastically changed to accommodate the new `status` command.  

# v2.13.6

### Fixed
- Fixed a bug in the contact command where the response message did not send.

# v2.13.5

### What's new?
- You will no longer need to view your bot debug logs from Heroku. `debug` will show you the recent logs within 24h through a series of embeds.
  - If you don't mind your data (may or may not be limited to: user ID, guild ID, bot name) be on the internet, `debug hastebin` will upload a formatted logs file to https://hasteb.in.
  - `debug clear` will clear the locally cached logs.
  - Local logs are automatically cleared at least once every 27h for bots hosted on Heroku.

### Fixed
- Will no longer show  `Unclosed client session` and `Task was destroyed but it is pending!` when the bot terminates.
- `thread.create` is now synchronous so that the first message sent can be queued to be sent as soon as a thread is created. 
    - This fixes a problem where if multiple messages are sent in quick succession, the first message sent (which triggers the thread creation) is not sent in order.
- Trying to reply to someone who has DMs disabled or has blocked the bot is now handled and the bot will send a message saying so. 

### Changed
- `print` is replaced by logging.
  - New environment variable introduced: `LOG_LEVEL`.
  - This influences the number of messages received in Heroku logs. 
  - Possible options, from least to most severe, are: `INFO`, `DEBUG`, `WARNING`, `ERROR`, `CRITICAL`.
  - In most cases, you can ignore this change.
- `on_error` and `CommandNotFound` are now logged.

# v2.13.4

### Changed
- `?contact` no longer raise a silent error in Heroku logs when the recipient is a bot. Now Modmail responds with an error message.

# v2.13.3

### Fixed
- Fixed a typo in the config options.

# v2.13.2

### Fixed
- Installing `requirements.txt` files in plugins.

# v2.13.1

### Fixed
- Reading `requirements.txt` files in plugins.

# v2.13.0

### What's new? 
- Plugins:
  - Think of it like addons! Anyone (with the skills) can create a plugin, make it public and distribute it. Add a welcome message to Modmail, or moderation commands? It's all up to your imagination!    Have a niche feature request that you think only your server would benefit from? Plugins are your go-to!
  - [Creating Plugins Documentation](https://github.com/kyb3r/modmail/wiki/Plugins).

# v2.12.5

### Fixed

- `config del` command will now work properly on self-hosted db bots.

# v2.12.4

### What's new?
- Named colors are now supported! Over 900 different common color names are recognized. A list of color names can be found in [core/_color_data.py](https://github.com/kyb3r/modmail/blob/master/core/_color_data.py).
  - Named colors can be set the same way as hex. But this can only be done through `config set`, which means database modifications will not work.
  - For example: `config set main_color yellowish green`.
- New config var `main_color` allows you to customize the main Modmail color (as requested by many). Defaults to Discord `blurple`.

# v2.12.3

### Fixed
- Patched a bug where `logs` sub-commands were accessible by anyone.
- Patched a bug where an error was raised if there was an open thread where the recipient had left the server.

Huge thanks to Sasiko for reporting these issues.

# v2.12.2

### Fixed
- Fixed a bug in self-hosted `update` command.

# v2.12.1

### Changed

- `logs search` now also searches usernames present in thread logs.

# v2.12.0

### Important
**In the future, the Modmail API (https://modmail.tk) will be deprecated. This is due to the fact that we are providing a free service without getting anything in return, and thus we do not have the resources to scale to accommodate for more users. 
We recommend using your own database for logs. In the future you will soon get a `backup` command so you can download all your pre-existing data and migrate to your own database.** 

### Changed
- A lot of painful code cleanup, which is good for us (the developers), but shouldn't affect you.
- The appearance of the `logs` command. Should be clearer with better info now.
- Bot owners get access to all commands regardless of server permissions.
- Blocked users no longer receive a message, only the blocked emoji will be sent.

### What's new?
- **Note:** The following commands only work if you are self-hosting your logs. We recommend you to use your own database.
- Log search queries, in the form of two new commands. 
- `logs search [query]` - this searches all log messages for a query string.
- `logs closed-by [user]` this returns all logs closed by a certain user

### Fixed
- `activity listening to music` no longer result in two "to"s ("listening to to music").
  - This may require you to change your activity message to accommodate this fix.
- A problem where `main_category_id` and `log_channel_id` weren't updated when their corresponding channel or category get deleted. 

# v2.11.0

### What's new?
- `loglink` command, returns the log link for the current thread.

# v2.10.2

### Changed
- Your logs now track and show edited messages.

# v2.10.1

### Changed
- Use reply author's top role for the mod tag by default.

# v2.10.0

### What's new?
- `anonreply` command to anonymously reply to the recipient. 
The username of the anonymous user defaults to the `mod_tag` (the footer text of a mod reply message). The avatar defaults the guild icon URL. However you can change both of these via the `anon_username`, `anon_avatar_url` and `anon_tag` config variables. 

### Changed
- Your bot now logs all messages sent in a thread channel, including discussions that take place. You can now toggle to view them in the log viewer app.

# v2.9.4

### Fixed
- Small bug due to a typo.

# v2.9.3

### Changed
- Forgot to enable custom embed colors.

### What's new?
- Ability to set a custom `mod_tag` (the text in the footer of the mod reply embed, which by default says "Moderator")

# v2.9.2

### Changed
- Improve format of thread info embed. Slightly cleaner and simpler now.
- All commands are now blurple instead of green.

### Fixed
- Bug where the close command wouldn't work if you didnt configure a log channel. 

### What's new?
- Ability to set your own custom `mod_color` and `recipient_color` for the thread message embeds.

# v2.9.1

### Changed
- Changed order of arguments for `contact`. This is so that you can use aliases to their full potential. 
- For example: 
  - `contact "Recruitment Category" @somedude`
- You can add an alias by doing: `alias add recruit contact "Recruitment Category"`.
  - Now you can use the alias via: `recruit @somedude`.

# v2.9.0

### What's new?
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

### What's new? 
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

### Note

- If your Modmail bot was set up a long time ago, you may experience an issue where messages were sent outside of the category.
  - To fix this, set `main_category_id` to the ID of the Modmail category.
  
# v2.7.0

### Changed

- `move` command now syncs thread channel permissions with the category that it was moved to.
- `contact` command now supports an optional category argument (where the thread channel will be created).

# v2.6.3

### Fixes
- Fixed small issue with finding thread.

# v2.6.2

### Fixes
- Fixed log URLs for self-hosting users.

# v2.6.1

### Fixed
- Replaced the testing `API_BASE_URL` with the actual URL.

# v2.6.0

### What's new?
- `threads` is now a default alias to `logs`.

### Changed
- Log URLs are moved to their own collection.
- Log URLs are now `https://logs.modmail.tk/LOGKEY`, no more numbers before the log key.
- We still support the numbers so as to not break everyone's URLs so quickly but both work at the moment.
- This is a huge change to the backend logging and there might be migration errors. If so, please contact us in our [discord server](https://discord.gg/2fMbf2N).

# v2.5.2

### Fixes
- Fixed a bug where requests sent when the API was not ready.

# v2.5.1

### Fixes
- Emergency patch to save config.

# v2.5.0

### Background
- Bots hosted by Heroku restart at least once every 27 hours.
- During this period, local caches are deleted, which results in the inability to set the scheduled close time to longer than 24 hours. This update resolves this issue. 
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

### Changed
 - Moved self-hosted log viewer to a separate repo.

# v2.4.2

### What's new?
- Ability to set your own Twitch URL for `streaming` activity status.

# v2.4.1

### Fixed
- Small bug in `activity` command.

# v2.4.0

### What's new?
- Added the `activity` command for setting the activity
- [PR #131](https://github.com/kyb3r/modmail/pull/131#issue-244686818) this supports multiple activity types (`playing`, `watching`, `listening` and `streaming`).

### Removed
- Removed the deprecated `status` command.
- This also means you will have to reset your bot status with the `activity` command, as `status` command is removed.

# v2.3.0

### What's new?
- Ability to self-host logs.

### Changed
- Improved format for log channel embeds.
- Roles are now comma-separated in info embed.
- This only applies to separate server setups.

### Fixed
- Bug in subscribe command.
  - It will now unsubscribe after a thread is closed.

# v2.2.0

### What's new?
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

### What's new?
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
- Fix a bug where blocked users were still able to message Modmail.

# v2.0.9

### What's new?
- Support for custom blocked and sent emoji.
- Use the `config set blocked_emoji [emoji]` or `sent_emoji` commands.

### Fixes
- Support multiple images and file attachments in one message.
- This is only possible on mobile so its good to handle it in code.

# v2.0.8

### What's new?
- Added the ability to use your own log channel.
  - You can do this via the `config set log_channel_id <id>` command.
- Added the ability to use your own main inbox category.
  - You can do this via the `config set main_category_id <id>` command.

### Changed
- You now have the ability to supply a reason when blocking a user.
- Blocked users are now stored in the database instead of in the channel topic.
  - This means you can delete the top channel in the Modmail category now (after migrating the currently blocked users).

# v2.0.7

### What's new?
- Added a `changelog` command to view the bot's changelog within discord.

### Changed
- `update` command now shows the latest changes directly from CHANGELOG.md.
- Auto update messages also show the latest changes from the GitHub repo.
- Removed "latest changes" section from the `about` command.

# v2.0.6

### Fixed
- Fix logs sending duplicated thread close logs.
- The bot will now tell you that a user is no longer in the server when you try to reply to a thread.
  - Before this, it looked like you replied to the thread, but in reality, the message was not sent.

# v2.0.5

### Changed
- `alias` command now checks if you are adding a valid alias-command combo.
- Deleting a channel manually will now correctly close the thread and post logs.

# v2.0.4

### Fixed
- Fixed a one-off bug where the channel topic disappears, but Modmail operations should still continue.
- Fixed `linked_message_id` issues.

# v2.0.3

### Fixed
- Thread creation embed now shows the correct number of past logs.
- If using a separate server setup, roles in the info embed now are shown as names instead of mentions.
  - This is due to the fact that you can't mention roles across servers.

# v2.0.2

### Security
- Made the `logs` command require "manage messages" permissions to execute.
  - Before this patch, anyone could use the `logs` commands.

# v2.0.1

### Changed
- Improved `block` / `unblock` commands.
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

### What's new?
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
