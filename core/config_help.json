{
  "twitch_url": {
    "default": "`https://www.twitch.tv/discordmodmail/`",
    "description": "This channel dictates the linked Twitch channel when the activity is set to \"Streaming\".",
    "examples": [
      "`{prefix}config set twitch_url https://www.twitch.tv/yourchannelname/`"
    ],
    "notes": [
      "This has no effect when the activity is not set to \"Streaming\".",
      "See also: `{prefix}help activity`."
    ]
  },
  "main_category_id": {
    "default": "`Modmail` (created with `{prefix}setup`)",
    "description": "This is the category where all new threads will be created.\n\nTo change the Modmail category, you will need to find the [category’s ID](https://support.discordapp.com/hc/en-us/articles/206346498).",
    "examples": [
      "`{prefix}config set main_category_id 9234932582312` (`9234932582312` is the category ID)"
    ],
    "notes": [
      "If the Modmail category ended up being non-existent/invalid, Modmail will break. To fix this, run `{prefix}setup` again or set `main_category_id` to a valid category.",
      "When the Modmail category is full, new channels will be created in the fallback category.",
      "See also: `fallback_category_id`."
    ]
  },
  "fallback_category_id": {
    "default": "`Fallback Modmail` (created when the main category is full)",
    "description": "This is the category that will hold the threads when the main category is full.\n\nTo change the Fallback category, you will need to find the [category’s ID](https://support.discordapp.com/hc/en-us/articles/206346498).",
    "examples": [
      "`{prefix}config set fallback_category_id 9234932582312` (`9234932582312` is the category ID)"
    ],
    "notes": [
      "If the Fallback category ended up being non-existent/invalid, Modmail will create a new one. To fix this, set `fallback_category_id` to a valid category.",
      "See also: `main_category_id`."
    ]
  },
  "prefix": {
    "default": "`?`",
    "description": "The prefix of the bot.",
    "examples": [
      "`{prefix}prefix !`",
      "`{prefix}config set prefix !`"
    ],
    "notes": [
      "If you forgot the bot prefix, Modmail will always respond to its mention (ping)."
    ]
  },
  "mention": {
    "default": "@here",
    "description": "This is the message above user information for when a new thread is created in the channel.",
    "examples": [
      "`{prefix}config set mention Yo~ Here's a new thread for ya!`",
      "`{prefix}mention Yo~ Here's a new thread for ya!`"
    ],
    "notes": [
      "Unfortunately, it's not currently possible to disable mention. You do not have to include a mention."
    ]
  },
  "main_color": {
    "default": "Discord Blurple [#7289DA](https://placehold.it/100/7289da?text=+)",
    "description": "This is the main color for Modmail (help/about/ping embed messages, subscribe, move, etc.).",
    "examples": [
      "`{prefix}config set main_color olive green`",
      "`{prefix}config set main_color 12de3a`",
      "`{prefix}config set main_color #12de3a`",
      "`{prefix}config set main_color fff`"
    ],
    "notes": [
      "Available color names can be found on [Taki's Blog](https://taaku18.github.io/modmail/colors/).",
      "See also: `error_color`, `mod_color`, `recipient_color`."
    ],
    "thumbnail": "https://placehold.it/100/7289da?text=+"
  },
  "error_color": {
    "default": "Discord Red [#E74C3C](https://placehold.it/100/e74c3c?text=+)",
    "description": "This is the color for Modmail when anything goes wrong, unsuccessful commands, or a stern warning.",
    "examples": [
      "`{prefix}config set error_color ocean blue`",
      "`{prefix}config set error_color ff1242`",
      "`{prefix}config set error_color #ff1242`",
      "`{prefix}config set error_color fa1`"
    ],
    "notes": [
      "Available color names can be found on [Taki's Blog](https://taaku18.github.io/modmail/colors/).",
      "See also: `main_color`, `mod_color`, `recipient_color`."
    ],
    "thumbnail": "https://placehold.it/100/e74c3c?text=+"
  },
  "user_typing": {
    "default": "Disabled",
    "description": "When this is set to `yes`, whenever the recipient user starts to type in their DM channel, the moderator will see “{bot.user.display_name} is typing…” in the thread channel.",
    "examples": [
      "`{prefix}config set user_typing yes`",
      "`{prefix}config set user_typing no`"
    ],
    "notes": [
      "See also: `mod_typing`."
    ]
  },
  "mod_typing": {
    "default": "Disabled",
    "description": "When this is set to `yes`, whenever a moderator starts to type in the thread channel, the recipient user will see \"{bot.user.display_name} is typing…\" in their DM channel.",
    "examples": [
      "`{prefix}config set mod_typing yes`",
      "`{prefix}config set mod_typing no`"
    ],
    "notes": [
      "See also: `mod_typing`."
    ]
  },
  "account_age": {
    "default": "No age threshold",
    "description": "The creation date of the recipient user account must be greater than the number of days, hours, minutes or any time-interval specified by this configuration.",
    "examples": [
      "`{prefix}config set account_age P12DT3H` (stands for 12 days and 3 hours in [ISO-8601 Duration Format](https://en.wikipedia.org/wiki/ISO_8601#Durations))",
      "`{prefix}config set account_age 3 days and 5 hours` (accepted readable time)"
    ],
    "notes": [
      "To remove this restriction, do `{prefix}config del account_age`.",
      "See also: `guild_age`."
    ]
  },
  "guild_age": {
    "default": "No age threshold",
    "description": "The join date of the recipient user into this server must be greater than the number of days, hours, minutes or any time-interval specified by this configuration.",
    "examples": [
      "`{prefix}config set guild_age P12DT3H` (stands for 12 days and 3 hours in [ISO-8601 Duration Format](https://en.wikipedia.org/wiki/ISO_8601#Durations))",
      "`{prefix}config set guild_age 3 days and 5 hours` (accepted readable time)"
    ],
    "notes": [
      "To remove this restriction, do `{prefix}config del guild_age`.",
      "See also: `account_age`."
    ]
  },
  "reply_without_command": {
    "default": "Disabled",
    "description": "Setting this configuration will make all non-command messages sent in the thread channel to be forwarded to the recipient without the need of `{prefix}reply`.",
    "examples": [
      "`{prefix}config set reply_without_command yes`",
      "`{prefix}config set reply_without_command no`"
    ],
    "notes": [
      "See also: `anon_reply_without_command`."
    ]
  },
  "anon_reply_without_command": {
    "default": "Disabled",
    "description": "Setting this configuration will make all non-command messages sent in the thread channel to be anonymously forwarded to the recipient without the need of `{prefix}reply`.",
    "examples": [
      "`{prefix}config set anon_reply_without_command yes`",
      "`{prefix}config set anon_reply_without_command no`"
    ],
    "notes": [
      "See also: `reply_without_command`."
    ]
  },
  "log_channel_id": {
    "default": "`#bot-logs` (created with `{prefix}setup`)",
    "description": "This is the channel where all log messages will be sent (ie. thread close message, update message, etc.).\n\nTo change the log channel, you will need to find the [channel’s ID](https://support.discordapp.com/hc/en-us/articles/206346498). The channel doesn’t necessary have to be under the `main_category`.",
    "examples": [
      "`{prefix}config set log_channel_id 9234932582312` (9234932582312 is the channel ID)"
    ],
    "notes": [
      "If the Modmail logging channel ended up being non-existent/invalid, no logs will be sent."
    ]
  },
  "sent_emoji": {
    "default": "✅",
    "description": "This is the emoji added to the message when when a Modmail action is invoked successfully (ie. DM Modmail, edit message, etc.).",
    "examples": [
      "`{prefix}config set sent_emoji ✨`"
    ],
    "notes": [
      "You can disable `sent_emoji` with `{prefix}config set sent_emoji disable`.",
      "Custom/animated emojis are also supported, however, the emoji must be added to the server.",
      "See also: `blocked_emoji`."
    ]
  },
  "blocked_emoji": {
    "default": "🚫",
    "description": "This is the emoji added to the message when when a Modmail action is invoked unsuccessfully (ie. DM Modmail when blocked, failed to reply, etc.).",
    "examples": [
      "`{prefix}config set blocked_emoji 🙅‍`"
    ],
    "notes": [
      "You can disable `blocked_emoji` with `{prefix}config set blocked_emoji disable`.",
      "Custom/animated emojis are also supported, however, the emoji must be added to the server.",
      "See also: `sent_emoji`."
    ]
  },
  "close_emoji": {
    "default": "🔒",
    "description": "This is the emoji the recipient can click to close a thread themselves. The emoji is automatically added to the `thread_creation_response` embed.",
    "examples": [
      "`{prefix}config set close_emoji 👍‍`"
    ],
    "notes": [
      "This will only have an effect when `recipient_thread_close` is enabled.",
      "See also: `recipient_thread_close`."
    ]
  },
  "recipient_thread_close": {
    "default": "Disabled",
    "description": "Setting this configuration will allow recipients to use the `close_emoji` to close the thread themselves.",
    "examples": [
      "`{prefix}config set recipient_thread_close yes`",
      "`{prefix}config set recipient_thread_close no`"
    ],
    "notes": [
      "The close emoji is dictated by the configuration `close_emoji`.",
      "See also: `close_emoji`."
    ]
  },
  "thread_auto_close_silently": {
    "default": "No",
    "description": "Setting this configuration will close silently when the thread auto-closes.",
    "examples": [
      "`{prefix}config set thread_auto_close_silently yes`",
      "`{prefix}config set thread_auto_close_silently no`"
    ],
    "notes": [
      "This will only have an effect when `thread_auto_close` is set.",
      "See also: `thread_auto_close`."
    ]
  },
  "thread_auto_close": {
    "default": "Never",
    "description": "Setting this configuration will close threads automatically after the number of days, hours, minutes or any time-interval specified by this configuration.",
    "examples": [
      "`{prefix}config set thread_auto_close P12DT3H` (stands for 12 days and 3 hours in [ISO-8601 Duration Format](https://en.wikipedia.org/wiki/ISO_8601#Durations))",
      "`{prefix}config set thread_auto_close 3 days and 5 hours` (accepted readable time)"
    ],
    "notes": [
      "To disable auto close, do `{prefix}config del thread_auto_close`.",
      "To prevent a thread from auto-closing, do `{prefix}close cancel`.",
      "See also: `thread_auto_close_silently`, `thread_auto_close_response`."
    ]
  },
  "thread_cooldown": {
    "default": "Never",
    "description": "Specify the time required for the recipient to wait before allowed to create a new thread.",
    "examples": [
      "`{prefix}config set thread_cooldown P12DT3H` (stands for 12 days and 3 hours in [ISO-8601 Duration Format](https://en.wikipedia.org/wiki/ISO_8601#Durations))",
      "`{prefix}config set thread_cooldown 3 days and 5 hours` (accepted readable time)"
    ],
    "notes": [
      "To disable thread cooldown, do `{prefix}config del thread_cooldown`."
    ]
  },
  "thread_auto_close_response": {
    "default": "\"This thread has been closed automatically due to inactivity after {{timeout}}.\"",
    "description": "This is the message to display when the thread when the thread auto-closes.",
    "examples": [
      "`{prefix}config set thread_auto_close_response Your close message here.`"
    ],
    "notes": [
      "Its possible to use `{{timeout}}` as a placeholder for a formatted timeout text.",
      "This will not have an effect when `thread_auto_close_silently` is enabled.",
      "Discord flavoured markdown is fully supported in `thread_auto_close_response`.",
      "See also: `thread_auto_close`, `thread_auto_close_silently`."
    ]
  },
  "thread_creation_response": {
    "default": "\"The staff team will get back to you as soon as possible.\"",
    "description": "This is the message embed content sent to the recipient upon the creation of a new thread.",
    "examples": [
      "`{prefix}config set thread_creation_response You will be contacted shortly.`"
    ],
    "notes": [
      "Discord flavoured markdown is fully supported in `thread_creation_response`.",
      "See also: `thread_creation_title`, `thread_creation_footer`, `thread_close_response`."
    ]
  },
  "thread_creation_footer": {
    "default": "\"Your message has been sent\"",
    "description": "This is the message embed footer sent to the recipient upon the creation of a new thread.",
    "examples": [
      "`{prefix}config set thread_creation_footer Please Hold...`"
    ],
    "notes": [
      "This is used in place of `thread_self_closable_creation_footer` when `recipient_thread_close` is enabled.",
      "See also: `thread_creation_title`, `thread_creation_response`, `thread_self_closable_creation_footer`, `thread_close_footer`."
    ]
  },
  "thread_self_closable_creation_footer": {
    "default": "\"Click the lock to close the thread\"",
    "description": "This is the message embed footer sent to the recipient upon the creation of a new thread.",
    "examples": [
      "`{prefix}config set thread_self_closable_creation_footer Please Hold...`"
    ],
    "notes": [
      "This is used in place of `thread_creation_footer` when `recipient_thread_close` is disabled.",
      "See also: `thread_creation_title`, `thread_creation_response`, `thread_creation_footer`."
    ]
  },
  "thread_creation_title": {
    "default": "\"Thread Created\"",
    "description": "This is the message embed title sent to the recipient upon the creation of a new thread.",
    "examples": [
      "`{prefix}config set thread_creation_title Hello!`"
    ],
    "notes": [
      "See also: `thread_creation_response`, `thread_creation_footer`, `thread_close_title`."
    ]
  },
  "thread_close_footer": {
    "default": "\"Replying will create a new thread\"",
    "description": "This is the message embed footer sent to the recipient upon the closure of a thread.",
    "examples": [
      "`{prefix}config set thread_close_footer Bye!`"
    ],
    "notes": [
      "See also: `thread_close_title`, `thread_close_response`, `thread_creation_footer`."
    ]
  },
  "thread_close_title": {
    "default": "\"Thread Closed\"",
    "description": "This is the message embed title sent to the recipient upon the closure of a thread.",
    "examples": [
      "`{prefix}config set thread_close_title Farewell!`"
    ],
    "notes": [
      "See also: `thread_close_response`, `thread_close_footer`, `thread_creation_title`."
    ]
  },
  "thread_close_response": {
    "default": "\"{{closer.mention}} has closed this Modmail thread\"",
    "description": "This is the message embed content sent to the recipient upon the closure of a thread.",
    "examples": [
      "`{prefix}config set thread_close_response Your message is appreciated!`"
    ],
    "notes": [
      "When `recipient_thread_close` is enabled and the recipient closed their own thread, `thread_self_close_response` is used instead of this configuration.",
      "You may use the `{{closer}}` variable for access to the [Member](https://discordpy.readthedocs.io/en/latest/api.html#discord.Member) that closed the thread.",
      "`{{loglink}}` can be used as a placeholder substitute for the full URL linked to the thread in the log viewer and `{{loglink}}` for the unique key (ie. s3kf91a) of the log.",
      "Discord flavoured markdown is fully supported in `thread_close_response`.",
      "See also: `thread_close_title`, `thread_close_footer`, `thread_self_close_response`, `thread_creation_response`."
    ]
  },
  "thread_self_close_response": {
    "default": "\"You have closed this Modmail thread.\"",
    "description": "This is the message embed content sent to the recipient upon the closure of a their own thread.",
    "examples": [
      "`{prefix}config set thread_self_close_response You have closed your own thread...`"
    ],
    "notes": [
      "When `recipient_thread_close` is disabled or the thread wasn't closed by the recipient, `thread_close_response` is used instead of this configuration.",
      "You may use the `{{closer}}` variable for access to the [Member](https://discordpy.readthedocs.io/en/latest/api.html#discord.Member) that closed the thread.",
      "`{{loglink}}` can be used as a placeholder substitute for the full URL linked to the thread in the log viewer and `{{loglink}}` for the unique key (ie. s3kf91a) of the log.",
      "Discord flavoured markdown is fully supported in `thread_self_close_response`.",
      "See also: `thread_close_title`, `thread_close_footer`, `thread_close_response`."
    ]
  },
  "thread_move_notify": {
    "default": "No",
    "description": "Notify the recipient if the thread was moved.",
    "examples": [
      "`{prefix}config set thread_move_notify yes`",
      "`{prefix}config set thread_move_notify no`"
    ],
    "notes": [
      "See also: `thread_move_response`."
    ]
  },
  "thread_move_response": {
    "default": "This thread has been moved.",
    "description": "This is the message to display to the user when the thread is moved.",
    "examples": [
      "`{prefix}config set thread_move_response This thread has been moved to another category for review!`"
    ],
    "notes": [
      "Only has an effect when `thread_move_notify` is on.",
      "See also: `thread_move_notify`."
    ]
  },
  "disabled_new_thread_title": {
    "default": "Not Delivered.",
    "description": "The title of the message embed when Modmail new thread creation is disabled and user tries to create a new thread.",
    "examples": [
      "`{prefix}config set disabled_new_thread_title Closed`"
    ],
    "notes": [
      "Only has an effect when `{prefix}disable` or `{prefix}disable all` is set.",
      "See also: `disabled_new_thread_response`, `disabled_new_thread_footer`, `disabled_current_thread_title`."
    ]
  },
  "disabled_new_thread_response": {
    "default": "We are not accepting new threads.",
    "description": "The body of the message embed when Modmail new thread creation is disabled and user tries to create a new thread.",
    "examples": [
      "`{prefix}config set disabled_new_thread_response Our working hours is between 8am - 6pm EST.`"
    ],
    "notes": [
      "Only has an effect when `{prefix}disable` or `{prefix}disable all` is set.",
      "See also: `disabled_new_thread_title`, `disabled_new_thread_footer`, `disabled_current_thread_response`."
    ]
  },
  "disabled_new_thread_footer": {
    "default": "Please try again later...",
    "description": "The footer of the message embed when Modmail new thread creation is disabled and user tries to create a new thread.",
    "examples": [
      "`{prefix}config set disabled_new_thread_footer Contact us later`"
    ],
    "notes": [
      "Only has an effect when `{prefix}disable` or `{prefix}disable all` is set.",
      "See also: `disabled_new_thread_title`, `disabled_new_thread_response`, `disabled_current_thread_footer`."
    ]
  },
  "disabled_current_thread_title": {
    "default": "Not Delivered.",
    "description": "The title of the message embed when Modmail DM is disabled and user DMs Modmail from existing thread.",
    "examples": [
      "`{prefix}config set disabled_current_thread_title Unavailable`"
    ],
    "notes": [
      "Only has an effect when `{prefix}disable all` is set.",
      "See also: `disabled_current_thread_response`, `disabled_current_thread_footer`, `disabled_new_thread_title`."
    ]
  },
  "disabled_current_thread_response": {
    "default": "We are not accepting any messages.",
    "description": "The body of the message embed when Modmail DM is disabled and user DMs Modmail from existing thread.",
    "examples": [
      "`{prefix}config set disabled_current_thread_response On break right now.`"
    ],
    "notes": [
      "Only has an effect when `{prefix}disable all` is set.",
      "See also: `disabled_current_thread_title`, `disabled_current_thread_footer`, `disabled_new_thread_response`."
    ]
  },
  "disabled_current_thread_footer": {
    "default": "Please try again later...",
    "description": "The footer of the message embed when Modmail DM is disabled and user DMs Modmail from existing thread.",
    "examples": [
      "`{prefix}config set disabled_current_thread_footer Message back!`"
    ],
    "notes": [
      "Only has an effect when `{prefix}disable all` is set.",
      "See also: `disabled_current_thread_title`, `disabled_current_thread_response`, `disabled_new_thread_footer`."
    ]
  },
  "recipient_color": {
    "default": "Discord Gold [#F1C40F](https://placehold.it/100/f1c40f?text=+)",
    "description": "This is the color of the messages sent by the recipient, this applies to messages received in the thread channel.",
    "examples": [
      "`{prefix}config set recipient_color dark beige`",
      "`{prefix}config set recipient_color cb7723`",
      "`{prefix}config set recipient_color #cb7723`",
      "`{prefix}config set recipient_color c4k`"
    ],
    "notes": [
      "Available color names can be found on [Taki's Blog](https://taaku18.github.io/modmail/colors/).",
      "See also: `mod_color`, `main_color`, `error_color`."
    ],
    "thumbnail": "https://placehold.it/100/f1c40f?text=+"
  },
  "mod_color": {
    "default": "Discord Green [#2ECC71](https://placehold.it/100/2ecc71?text=+)",
    "description": "This is the color of the messages sent by the moderators, this applies to messages within in the thread channel and the DM thread messages received by the recipient.",
    "examples": [
      "`{prefix}config set mod_color dark beige`",
      "`{prefix}config set mod_color cb7723`",
      "`{prefix}config set mod_color #cb7723`",
      "`{prefix}config set mod_color c4k`"
    ],
    "notes": [
      "Available color names can be found on [Taki's Blog](https://taaku18.github.io/modmail/colors/).",
      "See also: `recipient_color`, `main_color`, `error_color`."
    ],
    "thumbnail": "https://placehold.it/100/2ecc71?text=+"
  },
  "mod_tag": {
    "default": "The moderator's highest role",
    "description": "This is the name tag in the “footer” section of the embeds sent by moderators in the recipient DM and thread channel.",
    "examples": [
      "`{prefix}config set mod_tag Moderator`"
    ],
    "notes": [
      "When the message is sent anonymously, `anon_tag` is used instead.",
      "See also: `anon_tag`."
    ]
  },
  "anon_username": {
    "default": "Fallback on `mod_tag`",
    "description": "This is the name in the “author” section of the embeds sent by anonymous moderators in the recipient DM.",
    "examples": [
      "`{prefix}config set anon_username Incognito Mod`"
    ],
    "notes": [
      "See also: `anon_avatar_url`, `anon_tag`."
    ],
    "image": "https://i.imgur.com/SKOC42Z.png"
  },
  "anon_avatar_url": {
    "default": "Server avatar",
    "description": "This is the avatar of the embeds sent by anonymous moderators in the recipient DM.",
    "examples": [
      "`{prefix}config set anon_avatar_url https://path.to/your/avatar.png` (you will need to upload the avatar to somewhere)"
    ],
    "notes": [
      "See also: `anon_username`, `anon_tag`."
    ],
    "image": "https://i.imgur.com/SKOC42Z.png"
  },
  "anon_tag": {
    "default": "\"Response\"",
    "description": "This is the name tag in the “footer” section of the embeds sent by anonymous moderators in the recipient DM.",
    "examples": [
      "`{prefix}config set anon_tag Support Agent`"
    ],
    "notes": [
      "See also: `anon_avatar_url`, `anon_username`, `mod_tag`."
    ],
    "image": "https://i.imgur.com/SKOC42Z.png"
  },
  "modmail_guild_id": {
    "default": "Fallback on `GUILD_ID`",
    "description": "The ID of the discord server where the threads channels should be created (receiving server).",
    "examples": [
    ],
    "notes": [
      "This configuration can only to be set through `.env` file or environment (config) variables."
    ]
  },
  "guild_id": {
    "default": "None, required",
    "description": "The ID of the discord server where recipient users reside (users server).",
    "examples": [
    ],
    "notes": [
      "This configuration can only to be set through `.env` file or environment (config) variables."
    ]
  },
  "log_url": {
    "default": "https://example.com/",
    "description": "The base log viewer URL link, leave this as-is to not configure a log viewer.",
    "examples": [
    ],
    "notes": [
      "This configuration can only to be set through `.env` file or environment (config) variables."
    ]
  },
  "log_url_prefix": {
    "default": "`/logs`",
    "description": "The path to your log viewer extending from your `LOG_URL`, set this to `/` to specify no extra path to the log viewer.",
    "examples": [
    ],
    "notes": [
      "This configuration can only to be set through `.env` file or environment (config) variables."
    ]
  },
  "mongo_uri": {
    "default": "None, required",
    "description": "A MongoDB connection string.",
    "examples": [
    ],
    "notes": [
      "This configuration can only to be set through `.env` file or environment (config) variables."
    ]
  },
  "owners": {
    "default": "None, required",
    "description": "A list of definite bot owners, use `{prefix}perms add level OWNER @user` to set flexible bot owners.",
    "examples": [
    ],
    "notes": [
      "This configuration can only to be set through `.env` file or environment (config) variables."
    ]
  },
  "token": {
    "default": "None, required",
    "description": "Your bot token as found in the Discord Developer Portal.",
    "examples": [
    ],
    "notes": [
      "This configuration can only to be set through `.env` file or environment (config) variables."
    ]
  },
  "log_level": {
    "default": "INFO",
    "description": "The logging level for logging to stdout.",
    "examples": [
    ],
    "notes": [
      "This configuration can only to be set through `.env` file or environment (config) variables."
    ]
  },
  "enable_plugins": {
    "default": "Yes",
    "description": "Whether plugins should be enabled and loaded into Modmail.",
    "examples": [
    ],
    "notes": [
      "This configuration can only to be set through `.env` file or environment (config) variables."
    ]
  }
}
