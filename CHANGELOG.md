# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project mostly adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html);
however, insignificant breaking changes do not guarantee a major version bump, see the reasoning [here](https://github.com/kyb3r/modmail/issues/319). If you're a plugin developer, note the "BREAKING" section.

# [UNRELEASED]

### Fixed
- `?alias make/create` as aliases to `?alias add`. This improves continuity between the bot and its command structure. ([PR #3195](https://github.com/kyb3r/modmail/pull/3195))
- Loading the blocked list with the `?blocked` command takes a long time when the list is large. ([PR #3242](https://github.com/kyb3r/modmail/pull/3242))

# v4.0.2

### Breaking

- Presence intent is now by-default OFF. You can turn it on by setting `ENABLE_PRESENCE_INTENT=true` in the environment variables.

### Fixed

- Not having a guild icon no longer raises an exception. ([PR #3235](https://github.com/kyb3r/modmail/pull/3235))
  - When no icon is set, use the default user icon.
- Resolved an issue where `?logs` doesn't work when the thread has no title. ([PR #3201](https://github.com/kyb3r/modmail/pull/3201))
- AttributeError raised when failing to forward a reaction. ([GH #3218](https://github.com/kyb3r/modmail/issues/3218))

### Changed

- Plain messages no longer forces `()` around the respondent text. ([PR #3234](https://github.com/kyb3r/modmail/pull/3234))
- Added workflow to automatically build Docker image ([PR #3232](https://github.com/kyb3r/modmail/pull/3228))
- Updated installation guide to reflect new preferred hosting methods

# v4.0.1

This is a hotfix release.

### Improved

- Error Messages

### Fixed

- Thread cooldown

# v4.0.0

### Breaking

- Modmail now requires [`Message Content` privileged intent](https://support-dev.discord.com/hc/en-us/articles/4404772028055-Message-Content-Privileged-Intent-for-Verified-Bots).
- Upgraded to discord.py v2.0 ([internal changes](https://discordpy.readthedocs.io/en/latest/migrating.html), [GH #2990](https://github.com/kyb3r/modmail/issues/2990)).
- Python 3.8 or higher is required.
- Asyncio changes ([gist](https://gist.github.com/Rapptz/6706e1c8f23ac27c98cee4dd985c8120))
- Plugin registry is purged and all developers have to re-apply due to breaking changes.

### Added

- `use_hoisted_top_role` config to use change how default mod tags work, see `v3.10.0#Added` for details. ([PR #3093](https://github.com/kyb3r/modmail/pull/3093))
- `require_close_reason` config to require a reason to close a thread. ([GH #3107](https://github.com/kyb3r/modmail/issues/3107))
- `plain_snippets` config to force all snippets to be plain. ([GH #3083](https://github.com/kyb3r/modmail/issues/3083))
- `?fpareply` and `?fpreply` to reply to messages with variables plainly.
- `use_nickname_channel_name` config to use nicknames instead of usernames for channel names. ([GH #3112](https://github.com/kyb3r/modmail/issues/3112))
- `use_random_channel_name` config to use random nicknames vaguely tied to user ID. It is unable to be computed in reverse. ([GH #3143](https://github.com/kyb3r/modmail/issues/3143))
- `show_log_url_button` config to show Log URL button. ([GH #3122](https://github.com/kyb3r/modmail/issues/3122))
- Select menus for certain paginators.
- `Title` field in `?logs`. ([GH #3142](https://github.com/kyb3r/modmail/issues/3142))
- Snippets can be used in aliases. ([GH #3108](https://github.com/kyb3r/modmail/issues/3108), [PR #3124](https://github.com/kyb3r/modmail/pull/3124))
- `?snippet make/create` as aliases to `?snippet add`. ([GH #3172](https://github.com/kyb3r/modmail/issues/3173), [PR #3174](https://github.com/kyb3r/modmail/pull/3174))

### Improved

- Modmail now uses per-server avatars if applicable. ([GH #3048](https://github.com/kyb3r/modmail/issues/3048))
- Use discord relative timedeltas. ([GH #3046](https://github.com/kyb3r/modmail/issues/3046))
- Use discord native buttons for all paginator sessions.
- `?help` and `?blocked` paginator sessions now have better multi-page UI.
- Autoupdate now automatically updates pipenv dependencies if possible.

### Fixed

- Several minor typos. ([PR #3095](https://github.com/kyb3r/modmail/pull/3095), [PR #3116](https://github.com/kyb3r/modmail/pull/3116))
- Certain cases where fallback categories were not working as intended. ([PR #3109](https://github.com/kyb3r/modmail/pull/3109))
- `?contact` would create in a random category in silent mode. ([GH #3091](https://github.com/kyb3r/modmail/issues/3091), [PR #3092](https://github.com/kyb3r/modmail/pull/3092))
- Certain cases where `?close` would fail if closer isn't in cache. ([GH #3104](https://github.com/kyb3r/modmail/issues/3104), [PR #3105](https://github.com/kyb3r/modmail/pull/3105))
- Stickers now work in Modmail.
- Large server sizes results in Guild.name == None. ([GH #3088](https://github.com/kyb3r/modmail/issues/3088))
- Attachments now work on plain replies. ([GH #3102](https://github.com/kyb3r/modmail/issues/3102))
- Support LOTTIE stickers. ([GH #3119](https://github.com/kyb3r/modmail/issues/3119))
- Editing notes now work. ([GH #3094](https://github.com/kyb3r/modmail/issues/3094))
- Commands now work in threads.
- Audit log searching now properly works.
- Old data causing `?blocked` to fail. ([GH #3131](https://github.com/kyb3r/modmail/issues/3131))
- Delete channel auto close functionality now works.
- Improved error handling for autoupdate. ([PR #3161](https://github.com/kyb3r/modmail/pull/3161))
- Skip loading of already-loaded cog. ([PR #3172](https://github.com/kyb3r/modmail/pull/3172))
- Respect plugin's `cog_command_error`. ([GH #3170](https://github.com/kyb3r/modmail/issues/3170), [PR #3178](https://github.com/kyb3r/modmail/pull/3178))
- Use silent as a typing literal for contacting. ([GH #3179](https://github.com/kyb3r/modmail/issues/3179))

### Internal

- Improve regex parsing of channel topics. ([GH #3114](https://github.com/kyb3r/modmail/issues/3114), [PR #3111](https://github.com/kyb3r/modmail/pull/3111))
- Add warning if deploying on a developmental version.
- Extensions are now loaded `on_connect`.
- MongoDB v5.0 clients are now supported. ([GH #3126](https://github.com/kyb3r/modmail/issues/3126))
- Bump python-dotenv to v0.20.0, support for python 3.10
- Bump emoji to v1.7.0
- Bump aiohttp to v3.8.1
- Bump lottie to v0.6.11
- Remove deprecated `core/decorators.py` from v3.3.0

# v3.10.5

### Internal

- Locked plugin registry version impending v4 release.

# v3.10.4

### Improved

- Thread genesis message now shows other recipients.

### Fixed

- `?snippet add` now properly blocks command names.

### Internal

- Set `LOG_DISCORD` environment variable to the logger level and log discord events.

# v3.10.3
This is a hotfix for contact command.

### Fixed

- Fixed a bug where contacting with no category argument defaults to the top category.

# v3.10.2
This is a hotfix for react to contact.

### Fixed

- React to contact now works properly.

# v3.10.1

This is a hotfix for the edit command.

### Fixed

- `?edit` now works properly.

# v3.10.0

v3.10 adds group conversations while resolving other bugs and QOL changes. It is potentially breaking to some plugins that adds functionality to threads.

### Breaking

- `Thread.recipient` (`str`) is now `Thread.recipients` (`List[str]`).
- `Thread.reply` now returns `mod_message, user_message1, user_message2`... It is no longer limited at a size 2 tuple.

### Added

- Ability to have group conversations with up to 5 users. ([GH #143](https://github.com/kyb3r/modmail/issues/143))
- Snippets are invoked case insensitively. ([GH #3077](https://github.com/kyb3r/modmail/issues/3077), [PR #3080](https://github.com/kyb3r/modmail/pull/3080))
- Default tags now use top hoisted role. ([GH #3014](https://github.com/kyb3r/modmail/issues/3014))
- New thread-related config - `thread_show_roles`, `thread_show_account_age`, `thread_show_join_age`, `thread_cancelled`, `thread_creation_contact_title`, `thread_creation_self_contact_response`, `thread_creation_contact_response`. ([GH #3072](https://github.com/kyb3r/modmail/issues/3072))
- `use_timestamp_channel_name` config to create thread channels by timestamp.

### Improved

- `?contact` now accepts a role or multiple users (creates a group conversation). ([GH #3082](https://github.com/kyb3r/modmail/issues/3082))
- Aliases are now supported in autotrigger. ([GH #3081](https://github.com/kyb3r/modmail/pull/3081))

### Fixed

- Certain situations where the internal thread cache breaks and spams new channels. ([GH #3022](https://github.com/kyb3r/modmail/issues/3022), [PR #3028](https://github.com/kyb3r/modmail/pull/3028))
- Blocked users are now no longer allowed to use `?contact` and react to contact. ([COMMENT #819004157](https://github.com/kyb3r/modmail/issues/2969#issuecomment-819004157), [PR #3027](https://github.com/kyb3r/modmail/pull/3027))
- UnicodeEncodeError will no longer be raised on Windows. ([PR #3043](https://github.com/kyb3r/modmail/pull/3043))
- Notifications are no longer duplicated when using both `?notify` and `subscribe`. ([PR #3015](https://github.com/kyb3r/modmail/pull/3015))
- `?contact` now works properly with both category and silent. ([GH #3076](https://github.com/kyb3r/modmail/issues/3076))
- `close_on_leave_reason` now works properly when `close_on_leave` is enabled. ([GH #3075](https://github.com/kyb3r/modmail/issues/3075))
- Invalid arguments are now properly catched and a proper error message is sent.
- Update database after resetting/purging all plugins. ([GH #3011](https://github.com/kyb3r/modmail/pull/3011))
- `thread_auto_close` timer now only resets on non-note and replies from mods. ([GH #3030](https://github.com/kyb3r/modmail/issues/3030))
- Deleted messages are now deleted on both ends. ([GH #3041](https://github.com/kyb3r/modmail/issues/3041), [@JerrieAries](https://github.com/kyb3r/modmail/commit/20b31f8e8b5497943513997fef788d72ae668438))
- Persistent notes are now properly deleted from the database. ([GH #3013](https://github.com/kyb3r/modmail/issues/3013))
- Modmail Bot is now recognized to have `OWNER` permission level. This affects what can be run in autotriggers.

### Internal

- Fix return types, type hints and unresolved references ([PR #3009](https://github.com/kyb3r/modmail/pull/3009))
- Reload thread cache only when it's the first on_ready trigger. ([GH #3037](https://github.com/kyb3r/modmail/issues/3037))
- `format_channel_name` is now extendable to plugins. Modify `Bot.format_channel_name(bot, author, exclude_channel=None, force_null=False):`. ([GH #2982](https://github.com/kyb3r/modmail/issues/2982))

# v3.9.5

### Internal

- Bumped discord.py to v1.7.3, updated all other packages to latest.
- More debug log files are now kept.
- Resolve SSL errors by retrying without SSL

# v3.9.4

### Fixed

- Certain cases where fallback categories were not working as intended. ([GH #3002](https://github.com/kyb3r/modmail/issues/3002), [PR #3003](https://github.com/kyb3r/modmail/pull/3003))
- There is now a proper message when trying to contact a bot.

### Improved

- `?mention` can now be disabled with `?mention disable`. ([PR #2993](https://github.com/kyb3r/modmail/pull/2993/files))
- `?mention` now allows vague entries such as `everyone` or `all`. ([PR #2993](https://github.com/kyb3r/modmail/pull/2993/files))

### Internal

- Change heroku python version to 3.9.4 ([PR #3001](https://github.com/kyb3r/modmail/pull/3001))

# v3.9.3

### Added

- New config: `use_user_id_channel_name`, when set to TRUE, channel names would get created with the recipient's ID instead of their name and discriminator.
  - This is now an option to better suit the needs of servers in Server Discovery

### Internal

- Signature of `format_channel_name` in core/util.py changed to:
  - `format_channel_name(bot, author, exclude_channel=None, force_null=False)`


# v3.9.2

### Improved

- Additional HostingMethods (i.e. DOCKER, PM2, SCREEN). Autoupdates are now disabled on all docker instances. ([GH #2977](https://github.com/kyb3r/modmail/issues/2977), [PR #2988](https://github.com/kyb3r/modmail/pull/2988))

### Fixed

- `user_typing` default in the config help is now correct.

# v3.9.1

### Internal

- `bot.run` now more gracefully handles closing, similar to how discord.py handles it.
  - No longer displays `PrivilegedIntentsRequired` exception when exiting when presence intent is disabled.

# v3.9.0

### Breaking

- `on_thread_initiate` and `on_thread_ready` events now have `thread, creator, category, initial_message` as additional arguments.

### Fixed

- `confirm_thread_creation` now properly works when a user opens a thread using react to contact. ([GH #2930](https://github.com/kyb3r/modmail/issues/2930), [PR #2971](https://github.com/kyb3r/modmail/pull/2971))
- `?disable all/new` now disables react to contact threads. ([GH #2969](https://github.com/kyb3r/modmail/issues/2969), [PR #2971](https://github.com/kyb3r/modmail/pull/2971))
- Ghost errors are no longer raised when threads are created using non-organic methods.

### Internal

- `thread.reply` now returns (msg_to_user, msg_to_thread). Can be useful in plugins.

# v3.8.6

### Added

- Ability to install local plugins without relying on git / external sources
  - Simply add your extension to plugins/@local, and use `?plugin add local/plugin-name` to load the plugin as normal
- Updated deps for requirements.min.txt and pyproject.toml

# v3.8.5

### Added

- `?msglink <message id>`, allows you to obtain channel + message ID for T&S reports. ([GH #2963](https://github.com/kyb3r/modmail/issues/2963), [PR #2964](https://github.com/kyb3r/modmail/pull/2964))
- `?mention disable/reset`, disables or resets mention on thread creation. ([PR #2951](https://github.com/kyb3r/modmail/pull/2951))

### Fixed

- Non-master/development branch deployments no longer cause errors to be raised.
- Autotriggers now can search for roles/channels in guild context. ([GH #2961](https://github.com/kyb3r/modmail/issues/2961))

# v3.8.4

This update is a quick hotfix for a weird behaviour experienced on 1 Feb 2021 where users were not properly cached.

### Fixed

- Corrupted data is no longer saved to thread cache.

# v3.8.2

### Fixed

- Retry with `null-discrim` if channel could not be created. ([GH #2934](https://github.com/kyb3r/modmail/issues/2934))
- Fix update notifications.
- Retrieve user from Discord API if user has left the server, resolving issues in `?block`. ([GH #2935](https://github.com/kyb3r/modmail/issues/2935), [PR #2936](https://github.com/kyb3r/modmail/pull/2936))
- IDs in `<member>` commands work now.

# v3.8.1

### Fixed

- Additional image uploads now render properly. ([PR #2933](https://github.com/kyb3r/modmail/pull/2933))
- `confirm_thread_creation` no longer raises unnecessary errors. ([GH #2931](https://github.com/kyb3r/modmail/issues/2931), [PR #2933](https://github.com/kyb3r/modmail/pull/2933))
- Autotriggers no longer sends attachments back. ([GH #2932](https://github.com/kyb3r/modmail/issues/2932))

# v3.8.0

### Added

- `update_notifications` configuration option to toggle bot autoupdate notifications. ([GH #2896](https://github.com/kyb3r/modmail/issues/2896))
- `?fareply`, anonymously reply with variables.
- `anonymous_snippets` config variable to toggle if snippets should be anonymous. ([GH #2905](https://github.com/kyb3r/modmail/issues/2905))
- `disable_updates` config variable to control if the update command should be disabled or not.
- `silent_alert_on_mention` to alert mods silently. ([GH #2907](https://github.com/kyb3r/modmail/issues/2907))
- Support for only the "Server Members" intent.

### Improved

- Added command validation to `autotrigger add/edit`.
- `GITHUB_TOKEN` is now no longer required in Heroku setups.
- Clearer error messages on reply fails.

### Fixed

- Mentioned `competing` as an activity type. ([PR #2902](https://github.com/kyb3r/modmail/pull/2902))
- Level permissions were not checked if command permissions were set.
- Regex autotriggers were not working if term was in the middle of strings.
- `?blocked` now no longers show blocks that have expired.
- Blocked roles will no longer trigger an error during unblock.
- Custom emojis are now supported in `confirm_thread_creation_deny`. ([GH #2916](https://github.com/kyb3r/modmail/issues/2916))
- Finding linked messages in replies work now. ([GH #2920](https://github.com/kyb3r/modmail/issues/2920), [Jerrie-Aries](https://github.com/kyb3r/modmail/issues/2920#issuecomment-751530495))
- Sending files in threads (non-images) now work. ([GH #2926](https://github.com/kyb3r/modmail/issues/2926))
- Deleting messages no longer shows a false error. ([GH #2910](https://github.com/kyb3r/modmail/issues/2910), [Jerrie-Aries](https://github.com/kyb3r/modmail/issues/2910#issuecomment-753557313))
- Display an error on [Lottie](https://airbnb.io/lottie/#/) stickers, instead of failing the send.
- `?perms get` now shows role/user names. ([PR #2927](https://github.com/kyb3r/modmail/pull/2927))

### Internal

- Make use of `git branch --show-current` to retrieve branch instead of using prerelease version check.
- Use discord.py 1.6.0 from PyPi instead of the development clone.

# v3.7.13

### Fixed

- Notes in config help are now optional.

# v3.7.12

### Fixed

- Bot was not responding to union errors.
- `?block [reason]` now works in threads.

# v3.7.11

### Improved

- Role block will now work better with seperate server setups.

### Fixed

- Bot not restarting after autoupdate on PM2.

### Internal

- Removed unnecessary loggings.

# v3.7.10

### Added

- Added `update_channel_id` to specify which channel autoupdate notifications were being sent to.
- Added `show_timestamp` to specify if timestamps should be displayed in message embeds. ([GH #2885](https://github.com/kyb3r/modmail/issues/2885))

# v3.7.9

### Fixed

- `perms add/remove` with permission levels should now work again. ([GH #2892](https://github.com/kyb3r/modmail/issues/2892), [PR #2893](https://github.com/kyb3r/modmail/pull/2893))

### Improved

- Clearer plugin debug messages when plugins are disabled

# v3.7.8

### Added

- Added `thread_contact_silently` to allow opening threads silently by default. ([PR #2887](https://github.com/kyb3r/modmail/pull/2887))

### Fixed
- Permission levels were not respected.
- `perms remove` was not working.
- `logs` and `block` would not recognise users in a seperate server setup.
- Custom emojis were not working with `confirm_thread_creation`.

### Internal
- Optimised `perms get`, bot should respond faster now.

# v3.7.7

### Added

- Added updating github fork if GITHUB_TOKEN was provided

### Fixed

- Skip blocked roles check if user is not in main guild.

# v3.7.6

### Fixed

- Autoupdate persists despite errors.
- Mention when normal thread created was not working. ([GH #2883](https://github.com/kyb3r/modmail/issues/2883))

# v3.7.5

### Fixed

- Close on emoji was not working.

# v3.7.3

### Fixed

- React to contact threads were treated like normal contact threads. ([GH #2881](https://github.com/kyb3r/modmail/issues/2881))

# v3.7.2

### Added

- Added `mention_channel_id` to specify which channel `alert_on_mention` was being sent to. ([GH #2880](https://github.com/kyb3r/modmail/issues/2880))

### Fixed

- `?config set` would not respond if an invalid key was provided.

# v3.7.1

### Fixed

- Bot will now leave a reaction on the react to contact message.
- Added docstring to selfcontact

# v3.7.0

### Added

- Plain replies functionality. Added commands `preply`, `pareply` and config `plain_reply_without_command`. ([GH #2872](https://github.com/kyb3r/modmail/issues/2872))
- Added `react_to_contact_message`, `react_to_contact_emoji` to allow users to create threads by reacting to a message.
- Added `thread_move_notify_mods` to mention all mods again after moving thread. ([GH #215](https://github.com/kyb3r/modmail/issues/215))
- Added `transfer_reactions` to link reactions between mods and users. ([GH #2763](https://github.com/kyb3r/modmail/issues/2763))
- Added `close_on_leave`, `close_on_leave_reason` to automatically close threads upon recipient leaving the server. ([GH #2757](https://github.com/kyb3r/modmail/issues/2757))
- Added `alert_on_mention` to mention mods upon a bot mention. ([GH #2833](https://github.com/kyb3r/modmail/issues/2833))
- Added `confirm_thread_creation`, `confirm_thread_creation_title`, `confirm_thread_response`, `confirm_thread_creation_accept`, `confirm_thread_creation_deny` to allow users to confirm that they indeed want to create a new thread. ([GH #2773](https://github.com/kyb3r/modmail/issues/2773))
- Support Gyazo image links in message embeds. ([GH #282](https://github.com/kyb3r/modmail/issues/282))
- Added `silent` argument to `?contact` to restore old behaviour.
- Added new functionality: If `?help` is sent, bot does checks on every command, `?help all` restores old behaviour. ([GH #2847](https://github.com/kyb3r/modmail/issues/2847))
- Added a way to block roles. ([GH #2753](https://github.com/kyb3r/modmail/issues/2753))
- Added `cooldown_thread_title`, `cooldown_thread_response` to customise message sent when user is on a creating thread cooldown. ([GH #2865](https://github.com/kyb3r/modmail/issues/2865))
- Added `?selfcontact` to allow users to open a thread. ([GH #2762](https://github.com/kyb3r/modmail/issues/2762))
- Support stickers and reject non-messages. (i.e. pin_add)
- Added support for thread titles, `?title`. ([GH #2838](https://github.com/kyb3r/modmail/issues/2838))
- Added `data_collection` to specify if bot metadata should be collected by Modmail developers.
- Added `?autotrigger`, `use_regex_autotrigger` config to specify keywords to trigger commands. ([GH #130](https://github.com/kyb3r/modmail/issues/130), [GH #649](https://github.com/kyb3r/modmail/issues/649))
- Added `?note persistent` that creates notes that are persistent for a user. ([GH #2842](https://github.com/kyb3r/modmail/issues/2842), [PR #2878](https://github.com/kyb3r/modmail/pull/2878))
- Autoupdates and `?update` which was removed in v3.0.0

### Fixed

- `?contact` now sends members a DM.
- `level_permissions` and `command_permissions` would sometimes be reset. ([GH #2856](https://github.com/kyb3r/modmail/issues/2856))
- Command truncated after && in alias. ([GH #2870](https://github.com/kyb3r/modmail/issues/2870))
- `on_plugins_ready` event for plugins works now.

### Improved

- Plugins installations have clearer error messages.
- `?move` now does not require exact category names, accepts case-insensitive and startswith names.

### Internal
- Use enums in config. ([GH #2821](https://github.com/kyb3r/modmail/issues/2821))
- `on_thread_close` event for plugins.
- `on_thread_reply` event for plugins.

# v3.6.2

### Fixed

- Plugins downloading requirements in virtual environments.


# v3.6.1

### Added

- Proper error message if privileged intents not explicitly granted to bot.


# v3.6.0

### Added

- Added `thread_move_title` to specify title of thread moved embed.
- Mark NSFW logs in log message. ([GH #2792](https://github.com/kyb3r/modmail/issues/2792))
- Icon for moderator that closed the thread in log message. ([GH #2828](https://github.com/kyb3r/modmail/issues/2828))
- Ability to set mentions via user/role ID. ([GH #2796](https://github.com/kyb3r/modmail/issues/2796))

### Changed

- `?move` now consumes rest in category name, which means `?move Long Category Name` works without quotes!
- `?help` shows "No command description" if no description provided. ([PR #2845](https://github.com/kyb3r/modmail/pull/2845))

### Fixed
- Unicode errors raised during windows selfhosting

### Internal

- Bump discord.py version to 1.5.1
- Explicitly state intents used for connection
- Use `--diff` for black CI instead of `--check` ([GH #2816](https://github.com/kyb3r/modmail/issues/2816))


# v3.5.0

Fixed discord.py issue.

### Added

- A confirmation when you manually delete a thread message embed.
- Config var `enable_eval` defaults true, set `enable_eval=no` to disable the eval command. ([GH #2803](https://github.com/kyb3r/modmail/issues/2803))
- Added `?plugins reset` command to completely reset everything related to plugins. This will fix some problems caused by broken plugins in the file system.
- Support private GitHub repos for plugins (thanks to @officialpiyush pr#2767)

### Changed

- Bump discord.py version to v1.3.3.
- Renamed `bot.owner_ids` to `bot.bot_owner_ids` as the attribute is now defined internally for team support.
- Deleting channel manually will now close the thread.
- Deleting messages will no longer cause the bot to produce warnings.
- Plugins will automatically be removed when it fails to load.
- Moved all database-related activities to clients.py under MongoDBClient, with possible future hook for additional database support. 
- `bot.db` is deprecated in favour of `bot.api.db` and will be removed in the future.
- Deprecated `bot.plugin_db.get_partition` in favour of `bot.api.get_plugin_partition` (not final).
- Deprecated `MONGO_URI` config var (but will keep support in the future) in favour of `CONNECTION_URI` and `DATABASE_TYPE`. Right now there is one supported database - "mongodb", which is the default.

### Fixed

- Plugins not loading in Windows OS. Now uses proactor event loop for asyncio which should fix this.


# v3.4.1

### Fixed

- Masked a bunch of noise errors when deleting messages.
- Added more checks for deleting messages.

### Breaking

- `thread_initiate` will be dispatched at the beginning of the setup process.
- `thread_create` is dispatched when the thread is registered as a thread by Modmail (i.e., when channel topic is edited).
- `thread_ready` is dispatched when a thread finishes its setup steps.


# v3.4.0

### Added

- Thread cooldown!
  - Set via the new config var `thread_cooldown`.
  - Specify a time for the recipient to wait before allowed to create another thread.
- Fallback Category (thanks to DAzVise PR#636)
  - Automatically created upon reaching the 50 channels limit.
  - Manually set fallback category with the config var `fallback_category_id`.
- "enable" and "disable" support for yes or no config vars.
- Added "perhaps you meant" section to `?config help`.
- Multi-command alias is now more stable. With support for a single quote escape `\"`.
- New command `?freply`, which behaves exactly like `?reply` with the addition that you can substitute `{channel}`, `{recipient}`, and `{author}` to be their respective values. 
- New command `?repair`, repair any broken Modmail thread (with help from @officialpiyush).
- Recipients get feedback when they edit their messages.
- Chained delete for DMs now comes with a message.
- poetry (in case someone needs it).

### Changed

- The look of alias and snippet when previewing.
- The database now saves the message ID of the thread embed, instead of the original message.
- Swapped the position of user and category for `?contact`.
- The log file will no longer grow infinitely large.
- A hard limit of a maximum of 25 steps for aliases.
- `?disable` is now `?disable new`.

### Fixed

- Setting config vars using human time wasn't working.
- Fixed some bugs with aliases.
- Fixed many issues with `?edit` and `?delete` and recipient message edit.
- Masked the error: "AttributeError: 'int' object has no attribute 'name'"
  - Channel delete event will not be checked until discord.py fixes this issue.
- Chained reaction add/remove.
- Chained delete for thread channels.

### Internal

- Commit to black format line width max = 99, consistent with PyLint.
- No longer requires shlex for alias parsing.
- New checks with thread create / find.
- No more flake8 and Travis.

# v3.3.2

### Fixed

- An oversight with the permission system.

# v3.3.1

### Emergency Patch

- Fixed a recent issue with an animation KeyError due to Discord API update.

# v3.3.0

### Important

- Recommend all users to unblock and re-block all blocked users upon updating to this release.

### Added

- Three new config vars:
  - `enable_plugins` (yes/no default yes)
    - When set to no, Modmail will not load plugins.
  - `error_color` (color format, defaults discord red)
    - The color of error messages.
  - `anon_reply_without_command` (yes/no default no) (Thanks to papiersnipper PR#288)
    - When set, all non-command messages sent to thread channels are forwarded to the recipient anonymously without the need of `?anonreply`.
    - This config takes precedence over `reply_without_command`.
- `?logs responded [user]` command. It will show all the logs that the user has sent a reply. (Thanks to papiersnipper PR#288)
  - `user` when not provided, defaults to the user who ran the command.
- Open threads in limbo now auto-close if Modmail cannot find the channel. Modmail does this check every time the bot restarts.
- Ability to disable new threads from getting created.
  - `?disable`.
- Ability to fully disable Modmail DM.
  - `?disable all`.
- To re-enable DM: `?enable`, and to see the current status: `?isenable`.
- This disabled Modmail interface is customizable with the following config vars:
  - `disabled_new_thread_title`
  - `disabled_new_thread_response`
  - `disabled_new_thread_footer`
  - `disabled_current_thread_title`
  - `disabled_current_thread_response`
  - `disabled_current_thread_footer`
- Ability to delete notes when providing their ID. (Thanks to papiersnipper PR#402)
- Ability to delete log entries. (Thanks to papiersnipper PR#402)

### Changed

- `?contact` no longer send the "thread created" message to where the command was run, instead, it's now sent to the newly created thread channel. (Thanks to DAzVise)
- Automatically delete notes command `?note` when there're no attachments attached.
- Embed author links used to be inaccessible in many cases, now:
  - `?anonreply`, `?reply`, and `?note` in the thread channel will link to the sender's profile.
  - `?reply` and the recipient's DM will also link the sender's profile.
  - `?anonreply` in DM channel will link to the first channel of the main guild.
- Plugins update (mostly internal).
  - `git` is no longer used to install plugins; it now downloads through zip files.
  - `?plugins enabled` renamed to `?plugins loaded` while `enabled` is still an alias to that command.
  - Reorganized plugins folder structure.
  - Logging / plugin-related messages change.
  - Updating one plugin will not update other plugins; repositories no longer separate plugins, but the plugin name itself.
- The help command is in alphabetical order grouped by permissions.
- Notes are no longer always blurple; it's set to `MAIN_COLOR` now.
- Added `?plugins update` for updating all installed plugins.
- Reintroduce flake8 and use bandit for security issues detection.
- Add Travis checks for 3.6 in Linux and 3.7 for macOS and Windows.
- Debug logs not logs eval commands.
- Presence updates 30 minutes instead of 45 now.
- Fixed an assortment of problems to do with `?block`.
- Existing aliases can be used when creating new aliases. (Thanks to papiersnipper PR#402)

### Internal

- Reworked `config.get` and `config.set`, it feeds through the converters before setting/getting.
  - To get/set the raw value, access through `config[]`.
- The prerelease naming scheme is now `x.x.x-devN`.
- `trigger_typing` has been moved to `core.utils.trigger_typing`, the original location is deprecated.
- Simpler status and activity logic.
- New logging logic.

# v3.2.2

Security update!

### Important

- Supporter permission users used to be able to "hack" snippets to reveal all your config vars, including your token and MongoURI.
- Implemented some changes to address this bug:
  - All customizable variables used in snippets, close messages, etc., using the `{}` syntax, now forbids chaining two or more attributes and attributes that start with `_`.
- We advise you to update to this version.
- If you felt your credentials had been leaked, consider changing your bot token / MongoURI.

# v3.2.1

### Fixed

- Can't set hex for main_color, recipient_color, etc.

### Added

- Discord colors by default when addressing them by names.

# v3.2.0

### Added

- Ability to change permission levels of individual commands.
  - See `?permissions override` for more information.
- `thread_move_notify` and `thread_move_response` to notify recipients if a thread is moved. (Thanks to Flufster PR#360)
- IDs of messages sent to Modmail are now viewable. (Thanks to Flufster PR#360)

### Fixed

- `?help <some sub command>`, will return `Perhaps you meant: <some sub command>`, now it's fixed.
  - For example, `?help add` used to return `Perhaps you meant: add`, now it wouldn't do this.
- Aliases and Permissions command names are always saved lowercase now.
- An improved Dockerfile.

### Internal

- Use regex to parse Changes, Added, Fixed, etc. and description.
- Adds `PermissionLevel.INVALID` when commands don't have a permission level.

# v3.1.1

### Fixed

- An issue when reading `config_help.json` for Windows users due to an encoding problem.

# v3.1.0

### Breaking

- `disable_recipient_thread_close` is removed, a new configuration variable `recipient_thread_close` replaces it which defaults to False.
- Truthy and falsy values for binary configuration variables are now interpreted respectfully.
- `LOG_URL_PREFIX` cannot be set to "NONE" to specify no additional path in the future, "/" is the new method.

### Added

- `?sfw`, mark a thread as "safe for work", undos `?nsfw`.
- New config variable, `thread_auto_close_silently`, when set to a truthy value, no message will be sent when a thread is auto-closed.
- New configuration variable `thread_self_closable_creation_footer` — the footer when `recipient_thread_close` is enabled.
- Added a minimalistic version of requirements.txt (named requirements.min.txt) that contains only the absolute minimum of Modmail.
  - For users having trouble with pipenv or any other reason.
- Multi-step alias, see `?help alias add`. Public beta testing might be unstable.
- Misc commands without cogs are now displayed in `?help`.
- `?help` works for alias and snippets.
- `?config help <config-name>` shows a help embed for the configuration.
- Support setting permissions for subcommands.
- Support numbers (1-5) as substitutes for Permission Level REGULAR - OWNER in `?perms` subcommands.

### Changes

- `thread_auto_close_response` has a configurable variable `{timeout}`.
- `?snippet` is now the default command name instead of `?snippets` (`?snippets` is still usable). This is to make this consistent with `?alias`/`?aliases`.
- `colorama` is no longer a necessity; this is due to some unsupported OS.
- Changelog command can now take a version argument to jump straight to the specified version.
- `?plugin enabled` results are now sorted alphabetically.
- `?plugin registry` results are now sorted alphabetically, helps users find plugins more easily.
- `?plugin registry page-number` plugin registry can specify a page number for quick access.
- A reworked interface for `?snippet` and `?alias`.
  - Add an `?snippet raw <name>` command for viewing the raw content of a snippet (escaped markdown).
  - Add an `?alias raw <name>` command for displaying the raw content of an alias (escaped markdown).
- The placeholder channel for the streaming status changed to https://www.twitch.tv/discordmodmail/.
- Removed unclear `rm` alias for some `remove` commands.
- Paginate `?config options`.
- All users configured with a permission level higher than REGULAR has access to the main Modmail category.
  - Category overrides also changes when a level is removed or added to a user or role.
- `@everyone` is now accepted for `?perms add`.

### Fixes

- `?notify` no longer carries over to the next thread.
- `discord.NotFound` errors for `on_raw_reaction_add`.
- `mod_typing` ~~and `user_typing`~~ (`user_typing` is now by-design to show) will no longer show when the user is blocked.
- Better `?block` usage message.
- Resolved errors when mods sent messages after a thread is closed somehow.
- Recipient join/leave server messages are limited to only the guild set by `GUILD_ID`.
- When creating snippets and aliases, it now checks if other snippets/aliases with the same name exist.
- Modmail looked for `config.json` in the wrong directory.

### Internal

- Removed supporting code for GitHub interaction.
- All default config values moved to `core/config.py`.
- `config.cache` is no longer accessible, use `config['key']` for getting, `config['key'] = value` for setting, `config.remove('key')` for removing.
- Dynamic attribute for configs are removed, must use `config['key']` or `config.get('key')`.
- Removed helper functions `info()` and `error()` for formatting logging, it's formatted automatically now.
- Bumped discord.py version to 1.2.3.
- Use discord tasks for metadata loop.
- More debug based logging.
- Reduce redundancies in `?perms` sub commands.
- paginator been split into `EmbedPaginatorSession` and `MessagePaginatorSession`, both subclassing `PaginatorSession`.

# v3.0.3

### Added

- New commands, `?alias edit <name> <target>` and `?snippets edit <name> <target>`.
  - They can be used to edit aliases and snippets, respectively.

# v3.0.2

### Added

- A new command, `?blocked whitelist <user>`, this command prevents users from getting blocked by any means.

### Changed

- Removed some aliases from `?oauth`.

# v3.0.1

### Fixed

- Many bugs with `thread_auto_close`.

# v3.0.0

### Added 

- `?sponsors` command will list sponsors.
- An alert will now be sent to the log channel if a thread channel fails to create. This could be due to a variety of problems such as insufficient permissions, or the category channel limit is met. 
- Threads will close automatically after some time when `thread_auto_close` is set.
- Custom closing messages can be configured with `thread_auto_close_response`.

### Breaking Changes

- Removed auto-update functionality and the `?update` command in favor of the [Pull app](https://github.com/apps/pull).

Read more about updating your bot [here](https://github.com/kyb3r/modmail/wiki/updating)

### Changed
- Channel names now can contain Unicode characters.
- Debug logs are now located in a different file for each bot. (Internal change) 
- Default cogs always appear first in the help command now.

### Fixed
- Editing notes now work, minor bug with edit command is fixed.
- Bug in the `?oauth` command where the response message fails to send when an ID is provided.
- Plugin requirement installation now works in virtual environments


# v2.24.1

### Fixed

Fixed a bug with branches and `?plugin update`.

# v2.24.0

### Added

Branch support for `?plugin add` and in the registry. Typically for developers.    

# v2.23.0

### Added 

Added a "Mutual servers" field to the genesis embed if:
a) The user is not in the main guild.
b) The user shares more than one server with the bot.

### Changed

Notes with the `?note` command are now automatically pinned within the thread channel.

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
  - Completely revamped help command, few users changes.
  - Removed ABC (internal).

# v2.20.0

### What's new? 

New `?oauth whitelist` command, which allows you to whitelist users so they can log in via discord to view logs. To set up oauth login for your logviewer app, check the logviewer [repo](https://github.com/kyb3r/logviewer).

# v2.19.1

### Changed

- Ability to force an update despite having the same version number. Helpful to keep up-to-date with the latest GitHub commit.
  - `?update force`.
- Plugin developers now have a new event called `on_plugin_ready`; this is a coroutine and is awaited when all plugins are loaded. Use `on_plugin_ready` instead of `on_ready` since `on_ready` will not get called in plugins.

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

Commands now have better error messages. Instead of sending the help message for a command when an argument fails to be converted, the bot now says like "User 'bob' not found" instead.

# v2.18.1

Un-deprecated the `OWNERS` config variable to support Discord developer team accounts.

# v2.18.0

### New Permissions System

- A brand new permission system! Replaced the old guild-based permissions (i.e., manage channels, manage messages), with the new system enables you to customize your desired permission level specific to a command or a group of commands for a role or user.
- There are five permission levels:
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
- and the other methods listed above.

To revoke permission, use `remove` instead of `add`.

To view all roles and users with permission for a permission level or command do:
-  `?permissions get command command-name`
-  `?permissions get level owner`

By default, all newly set up Modmail will have `OWNER` set to the owner of the bot, and `REGULAR` set to @everyone.

### Breaking

When updating to this version, all prior permission settings with guild-based permissions will be invalidated. You will need to convert to the above system.
`OWNERS` will also get removed; you will need to set owners through `?permissions add level owner 212931293123129` or any way listed above.

### New Command

- A `?delete` command, which is an alternative to manually deleting a message. This command is created to no longer require "manage messages" permission to recall thread messages.

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

How Modmail checks if a channel is a thread: 

1. The bot first checks if the channel topic is in the format `User ID: XXXX`, this means it is a thread.
2. If a channel topic is not found, the bot searches through the message history of a channel to find the thread creation embed. This step should never yield a thread for an average user. Still, in the case of another bot messing up the channel topic (happened to a user before), this extra step was added. 

# v2.17.0

### What's new?

Added a config option `reply_without_command`, which, when present, enables the bot to forward any message sent in a thread channel to the recipient. (Replying without using a command)

To enable this functionality, do `?config set reply_without_command true` and to disable it, use `?config del reply_without_command`.

### Changed

The `move` command now only requires `manage_messages` perms instead of `manage_channels`.

# v2.16.1

### Fixed

An issue where a scheduled close would not execute over a long time if the recipient no shares any servers with the bot.

# v2.16.0

### Changed

All support for Modmail API (api.modmail.tk) has terminated. 
If you're still using api.modmail.tk, you will need to migrate to the self-hosted database
option ASAP. Your bot will not work unless you switch to the self-hosted option. Refer to the installation tutorial for information regarding self-hosted Modmail.

If a member leaves/joins (again) while they are a recipient of a thread, a message will be sent to notify you that this has occurred.

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
- `logkey` - the key for the thread logs, e.g. (`5219ccc82ad4`)
- `loglink` - the full link to the thread logs, e.g. (`https://logwebsite.com/logs/5219ccc82ad4`)

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

Added the ability to disable the `sent_emoji` and `blocked_emoji` when a user messages Modmail.

You can do this via `?config set sent_emoji disable`.

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
  - You can set `account_age` using `config set account_age time` where "time" can be a simple human-readable time string or an ISO-8601 Duration Format string.

### Changed
- `?block` reason cannot start with `System Message: ` as it is now reserved for internal user blocking.
- `?block`, like `?close`, now supports a block duration (temp blocking).

# v2.13.10

### Fixed
- Fixed an issue where status and activity do not work if they were modified wrongly in the database.
  - This was primarily an issue for older Modmail users, as the old `status` configuration variable clashes with the new `status` variable.

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
  - If you want the bot to type in the thread channel if the user is also typing, add the config variable `user_typing` and set it to "yes" or "true". Use `config del` to disable the functionality. The same thing in reverse is also possible if you want the user to see the bot type when someone is typing in the thread channel add the `mod_typing` config variable.
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
  - If you don't mind your data (may or may not be limited to user ID, guild ID, bot name) be on the internet, `debug hastebin` will upload a formatted logs file to https://hasteb.in.
  - `debug clear` will clear the locally cached logs.
  - Local logs are automatically erased at least once every 27h for bots hosted on Heroku.

### Fixed
- Will no longer show  `Unclosed client session` and `Task was destroyed, but it is pending!` when the bot terminates.
- `thread.create` is now synchronous so that the first message sent can be queued to be sent as soon as a thread is created. 
    - This fixes a problem where if multiple messages are sent in quick succession, the first message sent (which triggers the thread creation) is not sent in order.
- Trying to reply to someone who has DMs disabled or has blocked the bot is now handled, and the bot will send a message saying so. 

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
  - Think of it like addons! Anyone (with the skills) can create a plugin, make it public and distribute it. Add a welcome message to Modmail, or moderation commands? It's all up to your imagination!   Have a niche feature request that you think only your server would benefit? Plugins are your go-to!
  - [Creating Plugins Documentation](https://github.com/kyb3r/modmail/wiki/Plugins).

# v2.12.5

### Fixed

- `config del` command will now work correctly on self-hosted DB bots.

# v2.12.4

### What's new?
- Named colors are now supported! Over 900 different common color names are recognized. A list of color names can be found in [core/_color_data.py](https://github.com/kyb3r/modmail/blob/master/core/_color_data.py).
  - Named colors can be set the same way as hex. But this can only be done through `config set`, which means database modifications will not work.
  - For example: `config set main_color yellowish green`.
- New config var `main_color` allows you to customize the main Modmail color (as requested by many). Defaults to Discord `blurple`.

# v2.12.3

### Fixed
- Patched a bug where `logs` sub-commands were accessible by anyone.
- Patched a bug where an error was raised when a thread is open where the recipient left the server.

Huge thanks to Sasiko for reporting these issues.

# v2.12.2

### Fixed
- Fixed a bug in self-hosted `?update` command.

# v2.12.1

### Changed

- `logs search` now also searches usernames present in thread logs.

# v2.12.0

### Important
**In the future, the Modmail API (https://modmail.tk) will be deprecated. This is because we are providing free service without getting anything in return. Thus we do not have the resources to scale to accommodate more users. 
We recommend using your own database for logs. In the future you will soon get a `backup` command so you can download all your pre-existing data and migrate to your own database.** 

### Changed
- A lot of painful code cleanup, which is good for us (the developers), but shouldn't affect you.
- The appearance of the `?logs` command. It should be clearer with better info now.
- Bot owners get access to all commands regardless of server permissions.
- Blocked users no longer receive a message, only the blocked emoji will be sent.

### What's new?
- **Note:** The following commands only work if you are self-hosting your logs. We recommend you to use your own database.
- Log search queries, in the form of two new commands. 
- `logs search [query]` - this searches all log messages for a query string.
- `logs closed-by [user]` this returns all logs closed by a particular user

### Fixed
- `activity listening to music` no longer results in two "to"s ("listening to to music").
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
The username of the anonymous user defaults to the `mod_tag` (the footer text of a mod reply message) — the avatar defaults to the guild icon URL. However, you can change both of these via the `anon_username`, `anon_avatar_url`, and `anon_tag` config variables. 

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
- Bug where the close command wouldn't work if you didn't configure a log channel. 

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
- New command `note` will add a system message to your thread logs. - - This is useful for noting the context of a conversation.

# v2.8.1

### Fixed
- Fixed bug where thread logs were getting duplicated when using the `contact` command.
- Fixed bug where the wrong key was used for logs, which caused some `log` command log links to point to an HTTP 404 Not Found.
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
  - This will save you from some trouble if, for whatever reason, your configuration gets messed up.

# v2.7.1

### Changed

- All reference to "modmail" / "Mod Mail" / "ModMail" are changed to "Modmail".
- `log_channel_id` is now part of the config upon `setup`.
- Added the ability to set where threads are created using the `main_category_id` configuration option.

### Note

- If your Modmail bot was set up a long time ago, you might experience an issue where messages were sent outside of the category.
  - To fix this, set `main_category_id` to the ID of the Modmail category.
  
# v2.7.0

### Changed

- `move` command now syncs thread channel permissions with the destination category.
- `contact` command now supports an optional category argument (where the thread channel will be created).

# v2.6.3

### Fixes
- Fixed small issue with finding threads.

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
- We still support the numbers to not break everyone's URLs so quickly, but both work at the moment.
- This is a huge change to the backend logging, and there might be migration errors. If so, please contact us in our [Discord server](https://discord.gg/2fMbf2N).

# v2.5.2

### Fixes
- Fixed a bug where requests sent when the API was not ready.

# v2.5.1

### Fixes
- Emergency patch to save configs.

# v2.5.0

### Background
- Bots hosted by Heroku restart at least once every 27 hours.
- During this period, local caches will be deleted, which results in the inability to set the scheduled close time to longer than 24 hours. This update resolves this issue. 
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
Fixed a bug in the `?activity` command where it would fail to set the activity on bot restart if the activity type was `playing`.

# v2.4.3

### Changed
 - Moved self-hosted log viewer to a separate repo.

# v2.4.2

### What's new?
- Ability to set your own Twitch URL for `streaming` activity status.

# v2.4.1

### Fixed
- Small bug in `?activity` command.

# v2.4.0

### What's new?
- Added the `?activity` command for setting the activity
- [PR #131](https://github.com/kyb3r/modmail/pull/131#issue-244686818) this supports multiple activity types (`playing`, `watching`, `listening`, and `streaming`).

### Removed
- Removed the deprecated `status` command.
- This also means you will have to reset your bot status with the `?activity` command, as the `?status` command was removed.

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
  - Once a thread message is received, you will be pinged once only.

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
- Ability to set a custom thread-creation-response message.
  - Via `config set thread_creation_response [message]`.

### Changed
- Improve `?logs` command format.
- Improve thread log channel messages to have more relevant info.
- Improve close command.
  - You can now close the thread after a delay and use a custom thread close message.
  - You also now can close a thread silently.

# v2.0.10

### Security
- Fix a bug where blocked users were still able to message Modmail.

# v2.0.9

### What's new?
- Support for custom blocked and sent emoji.
- Use the `config set blocked_emoji [emoji]` or `sent_emoji` commands.

### Fixes
- Support multiple images and file attachments in one message.
- This is only possible on mobile, so its good to handle it in code.

# v2.0.8

### What's new?
- Added the ability to use your own log channel.
  - You can do this via the `config set log_channel_id <id>` command.
- Added the ability to use your own main inbox category.
  - You can do this via the `config set main_category_id <id>` command.

### Changed
- You can now supply a reason when blocking a user.
- Blocked users are now stored in the database instead of in the channel topic.
  - This means you can delete the top channel in the Modmail category now (after migrating the currently blocked users).

# v2.0.7

### What's new?
- Added a `changelog` command to view the bot's changelog within discord.

### Changed
- `update` command now shows the latest changes directly from CHANGELOG.md.
- Auto-update messages also show the latest changes from the GitHub repo.
- Removed the "latest changes" section from the `about` command.

# v2.0.6

### Fixed
- Fix logs sending duplicated thread close logs.
- The bot will now tell you that a user is no longer in the server when you try to reply to a thread.
  - Before this, it looked like you replied to the thread, but in reality, the message was not sent.

# v2.0.5

### Changed
- `alias` command now checks if you are adding a valid alias-command combo.
- Manually deleting a channel will now correctly close the thread and post logs.

# v2.0.4

### Fixed
- Fixed a one-off bug where the channel topic disappears, but Modmail operations should continue.
- Fixed `linked_message_id` issues.

# v2.0.3

### Fixed
- The thread creation embed now shows the correct number of past logs.
- If using a separate server setup, roles in the info embed now are shown as names instead of mentions.
  - This is because you can't mention roles across servers.

# v2.0.2

### Security
- Made the `logs` command require "manage messages" permissions to execute.
  - Before this patch, anyone could use the `logs` commands.

# v2.0.1

### Changed
- Improved `block` / `unblock` commands.
  - They now take a more comprehensive range of arguments: usernames, nicknames, mentions, and user IDs.

### Fixed
- Setup command now configures permissions correctly so that the bot will always be able to see the main operations category.

# v2.0.0

This release introduces the use of our centralized [API service](https://github.com/kyb3r/webserver) to enable dynamic configuration, auto-updates, and thread logs.
To use this release, you must acquire an API token from https://modmail.tk.
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
