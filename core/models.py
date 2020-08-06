import logging
import re
import sys
from enum import IntEnum
from logging.handlers import RotatingFileHandler
from string import Formatter

import sqlalchemy
from pymongo import IndexModel, ASCENDING, DESCENDING, TEXT
from sqlalchemy import Table, Column, Index, MetaData, ForeignKeyConstraint, func
from sqlalchemy.sql.expression import text
from umongo import Document, fields, validate

import discord
from discord.ext import commands

import _string

try:
    from colorama import Fore, Style
except ImportError:
    Fore = Style = type("Dummy", (object,), {"__getattr__": lambda self, item: ""})()


class PermissionLevel(IntEnum):
    OWNER = 5
    ADMINISTRATOR = 4
    ADMIN = 4
    MODERATOR = 3
    MOD = 3
    SUPPORTER = 2
    RESPONDER = 2
    REGULAR = 1
    INVALID = -1


class InvalidConfigError(commands.BadArgument):
    def __init__(self, msg, *args):
        super().__init__(msg, *args)
        self.msg = msg

    @property
    def embed(self):
        # Single reference of Color.red()
        return discord.Embed(title="Error", description=self.msg, color=discord.Color.red())


class ModmailLogger(logging.Logger):
    @staticmethod
    def _debug_(*msgs):
        return f'{Fore.CYAN}{" ".join(msgs)}{Style.RESET_ALL}'

    @staticmethod
    def _info_(*msgs):
        return f'{Fore.LIGHTMAGENTA_EX}{" ".join(msgs)}{Style.RESET_ALL}'

    @staticmethod
    def _error_(*msgs):
        return f'{Fore.RED}{" ".join(msgs)}{Style.RESET_ALL}'

    def debug(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.DEBUG):
            self._log(logging.DEBUG, self._debug_(msg), args, **kwargs)

    def info(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.INFO):
            self._log(logging.INFO, self._info_(msg), args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.WARNING):
            self._log(logging.WARNING, self._error_(msg), args, **kwargs)

    def error(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.ERROR):
            self._log(logging.ERROR, self._error_(msg), args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        if self.isEnabledFor(logging.CRITICAL):
            self._log(logging.CRITICAL, self._error_(msg), args, **kwargs)

    def line(self, level="info"):
        if level == "info":
            level = logging.INFO
        elif level == "debug":
            level = logging.DEBUG
        else:
            level = logging.INFO
        if self.isEnabledFor(level):
            self._log(
                level,
                Fore.BLACK + Style.BRIGHT + "-------------------------" + Style.RESET_ALL,
                [],
            )


logging.setLoggerClass(ModmailLogger)
log_level = logging.INFO
loggers = set()

ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(log_level)
formatter = logging.Formatter(
    "%(asctime)s %(name)s[%(lineno)d] - %(levelname)s: %(message)s", datefmt="%m/%d/%y %H:%M:%S"
)
ch.setFormatter(formatter)

ch_debug = None


def getLogger(name=None) -> ModmailLogger:
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.addHandler(ch)
    if ch_debug is not None:
        logger.addHandler(ch_debug)
    loggers.add(logger)
    return logger


class FileFormatter(logging.Formatter):
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

    def format(self, record):
        record.msg = self.ansi_escape.sub("", record.msg)
        return super().format(record)


def configure_logging(name, level=None):
    global ch_debug, log_level
    ch_debug = RotatingFileHandler(name, mode="a+", maxBytes=48000, backupCount=1)

    formatter_debug = FileFormatter(
        "%(asctime)s %(name)s[%(lineno)d] - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    ch_debug.setFormatter(formatter_debug)
    ch_debug.setLevel(logging.DEBUG)

    if level is not None:
        log_level = level

    ch.setLevel(log_level)

    for logger in loggers:
        logger.setLevel(log_level)
        logger.addHandler(ch_debug)


class _Default:
    pass


Default = _Default()


class SafeFormatter(Formatter):
    def get_field(self, field_name, args, kwargs):
        first, rest = _string.formatter_field_name_split(field_name)

        try:
            obj = self.get_value(first, args, kwargs)
        except (IndexError, KeyError):
            return "<Invalid>", first

        # loop through the rest of the field_name, doing
        #  getattr or getitem as needed
        # stops when reaches the depth of 2 or starts with _.
        try:
            for n, (is_attr, i) in enumerate(rest):
                if n >= 2:
                    break
                if is_attr:
                    if str(i).startswith("_"):
                        break
                    obj = getattr(obj, i)
                else:
                    obj = obj[i]
            else:
                return obj, first
        except (IndexError, KeyError):
            pass
        return "<Invalid>", first


class UserMongoModel(Document):
    class Meta:
        collection_name = "logs_user"
        indexes = ["name"]

    _id = fields.ObjectIdField(default=fields.ObjectId)
    id = fields.StringField(
        validate=validate.Length(max=24), required=True, unique=True
    )  # models.CharField(max_length=24, primary_key=True)
    name = fields.StringField(
        validate=validate.Length(max=32), required=True
    )  # models.CharField(max_length=32)
    discriminator = fields.StringField(
        validate=validate.Length(equal=4), required=True
    )  # models.CharField(max_length=4)
    avatar_url = fields.StringField(
        validate=validate.Length(max=120), required=True
    )  # models.CharField(max_length=120)  # shouldn't be above 105


metadata = MetaData()

UserSQLModel = Table(
    "logs_user",
    metadata,
    Column("id", sqlalchemy.String(24), primary_key=True),
    Column("name", sqlalchemy.String(32)),
    Column("discriminator", sqlalchemy.String(4)),
    Column("avatar_url", sqlalchemy.String(120)),
)
Index("idx_user_name", UserSQLModel.c.name)


class AttachmentMongoModel(Document):
    class Meta:
        collection_name = "logs_attachment"
        indexes = ["message", "sender"]

    _id = fields.ObjectIdField(default=fields.ObjectId)
    id = fields.StringField(
        validate=validate.Length(max=24), required=True, unique=True
    )  # models.CharField(max_length=24, primary_key=True)
    filename = fields.StringField(
        validate=validate.Length(max=32), default="attachment"
    )  # models.CharField(max_length=255)  # kind limit
    is_image = fields.BooleanField(default=True)  # models.BooleanField()
    size = fields.IntegerField(
        validate=validate.Range(max=2 ** 32 / 2 - 1, min=-(2 ** 32) / 2 + 1), default=-1
    )  # models.IntegerField()
    url = fields.StringField(
        validate=validate.Length(max=340), required=True
    )  # models.CharField(max_length=340)  # 85 + 255
    message = fields.ReferenceField("MessageMongoModel", required=True)
    sender = fields.ReferenceField("UserMongoModel", required=True)


AttachmentSQLModel = Table(
    "logs_attachment",
    metadata,
    Column("id", sqlalchemy.String(24), primary_key=True),
    Column("filename", sqlalchemy.String(32), server_default="uploaded_file"),
    Column("is_image", sqlalchemy.Boolean, server_default=text("TRUE")),
    Column("size", sqlalchemy.Integer, server_default=text("-1")),
    Column("url", sqlalchemy.String(340)),
    Column("message_id", sqlalchemy.String(24)),
    Column("sender_id", sqlalchemy.String(24)),
    ForeignKeyConstraint(
        ["message_id"], ["logs_message.id"], onupdate="CASCADE", ondelete="CASCADE"
    ),
    ForeignKeyConstraint(["sender_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"),
)
Index("idx_attachment_message_id", AttachmentSQLModel.c.message_id)
Index("idx_attachment_sender_id", AttachmentSQLModel.c.sender_id)


class MessageMongoModel(Document):
    class Meta:
        collection_name = "logs_message"
        indexes = [
            IndexModel([("content", TEXT), ("bot", ASCENDING)]),
            IndexModel([("author", ASCENDING), ("type", ASCENDING), ("author_mod", ASCENDING)]),
            IndexModel([("timestamp", DESCENDING)]),
            "bot",
            "log",
        ]

    _id = fields.ObjectIdField(default=fields.ObjectId)
    id = fields.StringField(validate=validate.Length(max=24), required=True, unique=True)
    bot = fields.ReferenceField("ConfigMongoModel", required=True, allow_none=True)
    timestamp = fields.DateTimeField(required=True)
    author = fields.ReferenceField("UserMongoModel", required=True)
    author_mod = fields.BooleanField(required=True)
    content = fields.StringField(
        validate=validate.Length(max=2048), default=""
    )  # models.TextField()
    type = fields.StringField(
        validate=validate.Length(max=20), default="thread_message", allow_none=False
    )  # models.CharField(max_length=20, null=True, default='thread_message')
    edited = fields.BooleanField(default=False)
    deleted = fields.BooleanField(default=False)
    log = fields.ReferenceField("LogMongoModel", required=True)


MessageSQLModel = Table(
    "logs_message",
    metadata,
    Column("id", sqlalchemy.String(24), primary_key=True),
    Column("bot_id", sqlalchemy.String(24), nullable=True),
    Column("timestamp", sqlalchemy.DateTime),
    Column("author_id", sqlalchemy.String(24)),
    Column("author_mod", sqlalchemy.Boolean),
    Column("content", sqlalchemy.String(2048), default=""),
    Column("type", sqlalchemy.String(20), default="thread_message"),
    Column("edited", sqlalchemy.Boolean, default=False, server_default=text("FALSE")),
    Column("deleted", sqlalchemy.Boolean, default=False, server_default=text("FALSE")),
    Column("log_key", sqlalchemy.String(16)),
    ForeignKeyConstraint(["bot_id"], ["config.id"], onupdate="CASCADE", ondelete="SET NULL"),
    ForeignKeyConstraint(["author_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"),
    ForeignKeyConstraint(["log_key"], ["logs.key"], onupdate="CASCADE", ondelete="CASCADE"),
)
Index("idx_message_bot_id", MessageSQLModel.c.bot_id)
Index("idx_message_log_key", MessageSQLModel.c.log_key)
Index("idx_message_timestamp", MessageSQLModel.c.timestamp.desc())
Index(
    "idx_message_author",
    MessageSQLModel.c.author_id,
    MessageSQLModel.c.author_mod,
    MessageSQLModel.c.type,
)
Index("idx_message_content", func.lower(MessageSQLModel.c.content), MessageSQLModel.c.bot_id)


class LogMongoModel(Document):
    class Meta:
        collection_name = "logs"
        indexes = [
            IndexModel([("channel_id", ASCENDING), ("bot", ASCENDING)]),
            IndexModel([("recipient", ASCENDING), ("bot", ASCENDING)]),
            IndexModel(
                [("creator", ASCENDING), ("created_at", DESCENDING), ("creator_mod", ASCENDING)]
            ),
            IndexModel([("closed_at", DESCENDING), ("closer", ASCENDING)]),
            "open",
            "bot",
        ]

    _id = fields.ObjectIdField(default=fields.ObjectId)
    key = fields.StringField(
        validate=validate.Length(max=16), required=True, unique=True
    )  # models.CharField(max_length=15, primary_key=True)  # shouldn't be above 12
    bot = fields.ReferenceField("ConfigMongoModel", required=True, allow_none=True)
    open = fields.BooleanField(default=True)  # models.BooleanField()
    created_at = fields.DateTimeField(required=True)  # models.DateTimeField()
    closed_at = fields.DateTimeField(
        allow_none=True, default=None
    )  # models.DateTimeField(null=True)
    channel_id = fields.StringField(
        validate=validate.Length(max=24), required=True, unique=True
    )  # models.CharField(max_length=24)
    guild_id = fields.StringField(
        validate=validate.Length(max=24), required=True
    )  # models.CharField(max_length=24)
    recipient = fields.ReferenceField("UserMongoModel", required=True)
    creator = fields.ReferenceField("UserMongoModel", required=True)
    creator_mod = fields.BooleanField(required=True)
    closer = fields.ReferenceField("UserMongoModel", allow_none=True)
    close_message = fields.StringField(
        allow_none=True, default=None
    )  # models.TextField(null=True)


LogSQLModel = Table(
    "logs",
    metadata,
    Column("key", sqlalchemy.String(16), primary_key=True),
    Column("bot_id", sqlalchemy.String(24), nullable=True),
    Column("open", sqlalchemy.Boolean, default=True),
    Column("created_at", sqlalchemy.DateTime),
    Column("closed_at", sqlalchemy.DateTime, default=None, nullable=True),
    Column("channel_id", sqlalchemy.String(24), unique=True),
    Column("guild_id", sqlalchemy.String(24)),
    Column("recipient_id", sqlalchemy.String(24)),
    Column("creator_id", sqlalchemy.String(24)),
    Column("creator_mod", sqlalchemy.Boolean),
    Column("closer_id", sqlalchemy.String(24), default=None, nullable=True),
    Column("close_message", sqlalchemy.Text, default=None, nullable=True),
    ForeignKeyConstraint(["bot_id"], ["config.id"], onupdate="CASCADE", ondelete="SET NULL"),
    ForeignKeyConstraint(
        ["recipient_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"
    ),
    ForeignKeyConstraint(["creator_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"),
    ForeignKeyConstraint(["closer_id"], ["logs_user.id"], onupdate="CASCADE", ondelete="CASCADE"),
)

Index("idx_logs_bot_id", LogSQLModel.c.bot_id)
Index("idx_logs_open", LogSQLModel.c.open)
Index("idx_logs_closed", LogSQLModel.c.closed_at.desc(), LogSQLModel.c.closer_id)
Index(
    "idx_logs_create",
    LogSQLModel.c.created_at.desc(),
    LogSQLModel.c.creator_id,
    LogSQLModel.c.creator_mod,
)
Index("idx_logs_recipient", LogSQLModel.c.recipient_id, LogSQLModel.c.bot_id)
Index("idx_logs_channel", LogSQLModel.c.channel_id, LogSQLModel.c.bot_id)


class ConfigMongoModel(Document):
    class Meta:
        collection_name = "config"

    _id = fields.ObjectIdField(default=fields.ObjectId)
    id = fields.StringField(
        validate=validate.Length(max=24), required=True, unique=True
    )  # models.CharField(max_length=24, primary_key=True)
    # activity
    twitch_url = fields.StringField(allow_none=True, default=None)
    # bot settings
    main_category_id = fields.StringField(
        validate=validate.Length(max=24), allow_none=True, default=None
    )
    fallback_category_id = fields.StringField(
        validate=validate.Length(max=24), allow_none=True, default=None
    )
    prefix = fields.StringField(validate=validate.Length(max=2048), allow_none=True, default=None)
    mention = fields.StringField(validate=validate.Length(max=2048), allow_none=True, default=None)
    main_color = fields.StringField(validate=validate.Length(max=7), allow_none=True, default=None)
    error_color = fields.StringField(
        validate=validate.Length(max=7), allow_none=True, default=None
    )
    user_typing = fields.BooleanField(allow_none=True, default=None)
    mod_typing = fields.BooleanField(allow_none=True, default=None)
    account_age = fields.StringField(allow_none=True, default=None)
    guild_age = fields.StringField(allow_none=True, default=None)
    thread_cooldown = fields.StringField(allow_none=True, default=None)
    reply_without_command = fields.BooleanField(allow_none=True, default=None)
    anon_reply_without_command = fields.BooleanField(allow_none=True, default=None)
    # logging
    log_channel_id = fields.StringField(
        validate=validate.Length(max=24), allow_none=True, default=None
    )
    # threads
    sent_emoji = fields.StringField(
        validate=validate.Length(max=340), allow_none=True, default=None
    )
    blocked_emoji = fields.StringField(
        validate=validate.Length(max=340), allow_none=True, default=None
    )
    close_emoji = fields.StringField(
        validate=validate.Length(max=340), allow_none=True, default=None
    )
    recipient_thread_close = fields.BooleanField(allow_none=True, default=None)
    thread_auto_close_silently = fields.BooleanField(allow_none=True, default=None)
    thread_auto_close = fields.StringField(allow_none=True, default=None)
    thread_auto_close_response = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    thread_creation_response = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    thread_creation_footer = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    thread_self_closable_creation_footer = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    thread_creation_title = fields.StringField(
        validate=validate.Length(max=256), allow_none=True, default=None
    )
    thread_close_footer = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    thread_close_title = fields.StringField(
        validate=validate.Length(max=256), allow_none=True, default=None
    )
    thread_close_response = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    thread_self_close_response = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    thread_move_notify = fields.BooleanField(allow_none=True, default=None)
    thread_move_response = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    disabled_new_thread_title = fields.StringField(
        validate=validate.Length(max=256), allow_none=True, default=None
    )
    disabled_new_thread_response = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    disabled_new_thread_footer = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    disabled_current_thread_title = fields.StringField(
        validate=validate.Length(max=256), allow_none=True, default=None
    )
    disabled_current_thread_response = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    disabled_current_thread_footer = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    # moderation
    recipient_color = fields.StringField(
        validate=validate.Length(max=7), allow_none=True, default=None
    )
    mod_color = fields.StringField(validate=validate.Length(max=7), allow_none=True, default=None)
    mod_tag = fields.StringField(validate=validate.Length(max=2048), allow_none=True, default=None)
    # anonymous message
    anon_username = fields.StringField(
        validate=validate.Length(max=256), allow_none=True, default=None
    )
    anon_avatar_url = fields.StringField(allow_none=True, default=None)
    anon_tag = fields.StringField(
        validate=validate.Length(max=2048), allow_none=True, default=None
    )
    # bot presence
    activity_message = fields.StringField(
        validate=validate.Length(max=128), allow_none=True, default=None
    )
    activity_type = fields.IntegerField(
        validate=validate.Range(max=2 ** 16 / 2 - 1, min=-(2 ** 16) / 2 + 1),
        allow_none=True,
        default=None,
    )
    status = fields.StringField(validate=validate.Length(max=12), allow_none=True, default=None)
    dm_disabled = fields.IntegerField(
        validate=validate.Range(max=2 ** 16 / 2 - 1, min=-(2 ** 16) / 2 + 1),
        allow_none=True,
        default=None,
    )
    # moderation
    oauth_whitelist = fields.StringField(allow_none=True, default=None)
    blocked = fields.StringField(allow_none=True, default=None)
    blocked_whitelist = fields.StringField(allow_none=True, default=None)
    command_permissions = fields.StringField(allow_none=True, default=None)
    level_permissions = fields.StringField(allow_none=True, default=None)
    override_command_level = fields.StringField(allow_none=True, default=None)
    # threads
    snippets = fields.StringField(allow_none=True, default=None)
    notification_squad = fields.StringField(allow_none=True, default=None)
    subscriptions = fields.StringField(allow_none=True, default=None)
    closures = fields.StringField(allow_none=True, default=None)
    # misc
    plugins = fields.StringField(allow_none=True, default=None)
    aliases = fields.StringField(allow_none=True, default=None)


ConfigSQLModel = Table(
    "config",
    metadata,
    Column("id", sqlalchemy.String(24), primary_key=True),
    Column("twitch_url", sqlalchemy.Text, nullable=True, default=None),
    Column("main_category_id", sqlalchemy.String(24), nullable=True, default=None),
    Column("fallback_category_id", sqlalchemy.String(24), nullable=True, default=None),
    Column("prefix", sqlalchemy.String(2048), nullable=True, default=None),
    Column("mention", sqlalchemy.String(2048), nullable=True, default=None),
    Column("main_color", sqlalchemy.String(7), nullable=True, default=None),
    Column("error_color", sqlalchemy.String(7), nullable=True, default=None),
    Column("user_typing", sqlalchemy.Boolean, nullable=True, default=None),
    Column("mod_typing", sqlalchemy.Boolean, nullable=True, default=None),
    Column("account_age", sqlalchemy.Text, nullable=True, default=None),
    Column("guild_age", sqlalchemy.Text, nullable=True, default=None),
    Column("thread_cooldown", sqlalchemy.Text, nullable=True, default=None),
    Column("reply_without_command", sqlalchemy.Boolean, nullable=True, default=None),
    Column("anon_reply_without_command", sqlalchemy.Boolean, nullable=True, default=None),
    Column("log_channel_id", sqlalchemy.String(24), nullable=True, default=None),
    Column("sent_emoji", sqlalchemy.String(340), nullable=True, default=None),
    Column("blocked_emoji", sqlalchemy.String(340), nullable=True, default=None),
    Column("close_emoji", sqlalchemy.String(340), nullable=True, default=None),
    Column("recipient_thread_close", sqlalchemy.Boolean, nullable=True, default=None),
    Column("thread_auto_close_silently", sqlalchemy.Boolean, nullable=True, default=None),
    Column("thread_auto_close", sqlalchemy.Text, nullable=True, default=None),
    Column("thread_auto_close_response", sqlalchemy.String(2048), nullable=True, default=None),
    Column("thread_creation_response", sqlalchemy.String(2048), nullable=True, default=None),
    Column("thread_creation_footer", sqlalchemy.String(2048), nullable=True, default=None),
    Column(
        "thread_self_closable_creation_footer",
        sqlalchemy.String(2048),
        nullable=True,
        default=None,
    ),
    Column("thread_creation_title", sqlalchemy.String(256), nullable=True, default=None),
    Column("thread_close_footer", sqlalchemy.String(2048), nullable=True, default=None),
    Column("thread_close_title", sqlalchemy.String(256), nullable=True, default=None),
    Column("thread_close_response", sqlalchemy.String(2048), nullable=True, default=None),
    Column("thread_self_close_response", sqlalchemy.String(2048), nullable=True, default=None),
    Column("thread_move_notify", sqlalchemy.Boolean, nullable=True, default=None),
    Column("thread_move_response", sqlalchemy.String(2048), nullable=True, default=None),
    Column("disabled_new_thread_title", sqlalchemy.String(256), nullable=True, default=None),
    Column("disabled_new_thread_response", sqlalchemy.String(2048), nullable=True, default=None),
    Column("disabled_new_thread_footer", sqlalchemy.String(2048), nullable=True, default=None),
    Column("disabled_current_thread_title", sqlalchemy.String(256), nullable=True, default=None),
    Column(
        "disabled_current_thread_response", sqlalchemy.String(2048), nullable=True, default=None
    ),
    Column("disabled_current_thread_footer", sqlalchemy.String(2048), nullable=True, default=None),
    Column("recipient_color", sqlalchemy.String(7), nullable=True, default=None),
    Column("mod_color", sqlalchemy.String(7), nullable=True, default=None),
    Column("mod_tag", sqlalchemy.String(2048), nullable=True, default=None),
    Column("anon_username", sqlalchemy.String(256), nullable=True, default=None),
    Column("anon_avatar_url", sqlalchemy.Text, nullable=True, default=None),
    Column("anon_tag", sqlalchemy.String(2048), nullable=True, default=None),
    Column("activity_message", sqlalchemy.String(128), nullable=True, default=None),
    Column("activity_type", sqlalchemy.SmallInteger, nullable=True, default=None),
    Column("status", sqlalchemy.String(12), nullable=True, default=None),
    Column("dm_disabled", sqlalchemy.SmallInteger, nullable=True, default=None),
    Column("oauth_whitelist", sqlalchemy.Text, nullable=True, default=None),
    Column("blocked", sqlalchemy.Text, nullable=True, default=None),
    Column("blocked_whitelist", sqlalchemy.Text, nullable=True, default=None),
    Column("command_permissions", sqlalchemy.Text, nullable=True, default=None),
    Column("level_permissions", sqlalchemy.Text, nullable=True, default=None),
    Column("override_command_level", sqlalchemy.Text, nullable=True, default=None),
    Column("snippets", sqlalchemy.Text, nullable=True, default=None),
    Column("notification_squad", sqlalchemy.Text, nullable=True, default=None),
    Column("subscriptions", sqlalchemy.Text, nullable=True, default=None),
    Column("closures", sqlalchemy.Text, nullable=True, default=None),
    Column("plugins", sqlalchemy.Text, nullable=True, default=None),
    Column("aliases", sqlalchemy.Text, nullable=True, default=None),
)
