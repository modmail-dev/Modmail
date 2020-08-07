import datetime
import secrets
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from os import path
from typing import Union, Optional

import ujson
from alembic import command
from alembic.config import Config
from databases import Database, DatabaseURL
from marshmallow.exceptions import ValidationError
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConfigurationError, OperationFailure
from sqlalchemy import select, and_, Table, Text, Column, String, Index, create_engine
from umongo import Instance, fields, Document, validate

from discord import Member, DMChannel, TextChannel, Message

from core.models import getLogger
from core import models


logger = getLogger(__name__)


class ApiClient(ABC):
    """
    This class represents the general request class for all type of clients.

    Parameters
    ----------
    bot : Bot
        The Modmail bot.

    Attributes
    ----------
    bot : Bot
        The Modmail bot.
    connection_uri : Union[DatabaseURL, str]
        The database connection URI.
    """

    def __init__(self, bot, connection_uri, db=None):
        self.bot = bot
        self.uri = connection_uri
        self.db = db
        self.session = bot.session

    @property
    def logs(self):
        return self.db.logs

    @staticmethod
    def get_key():
        return secrets.token_hex(7)  # hex length of 14

    @abstractmethod
    async def connect(self) -> None:
        return NotImplemented

    @abstractmethod
    async def disconnect(self) -> None:
        return NotImplemented

    @abstractmethod
    async def get_config(self) -> dict:
        return NotImplemented

    @abstractmethod
    async def update_config(self, data: dict) -> None:
        return NotImplemented

    @abstractmethod
    async def get_log_messages(
        self,
        *,
        log_key: str = None,
        channel_id: Union[str, int] = None,
        limit: int = 5,
        filter_types: list = None,
    ) -> list:
        return NotImplemented

    @abstractmethod
    async def get_log_recipient(
        self, *, log_key: str = None, channel_id: Union[str, int] = None
    ) -> dict:
        return NotImplemented

    @abstractmethod
    async def get_log_creator(
        self, *, log_key: str = None, channel_id: Union[str, int] = None
    ) -> dict:
        return NotImplemented

    @abstractmethod
    async def get_log_closer(
        self, *, log_key: str = None, channel_id: Union[str, int] = None
    ) -> Optional[dict]:
        return NotImplemented

    @abstractmethod
    async def get_message_author(self, msg_id: Union[str, int]) -> dict:
        return NotImplemented

    @abstractmethod
    async def get_message_attachments(self, msg_id: Union[str, int]) -> list:
        return NotImplemented

    @abstractmethod
    async def get_user_logs(self, user_id: Union[str, int], limit: int = 0) -> list:
        return NotImplemented

    @abstractmethod
    async def get_latest_user_log(self, user_id: Union[str, int]) -> Optional[dict]:
        return NotImplemented

    @abstractmethod
    async def get_open_logs(self) -> list:
        return NotImplemented

    @abstractmethod
    async def get_log_link(self, channel_id: Union[str, int]) -> str:
        return NotImplemented

    @abstractmethod
    async def create_log_entry(
        self, recipient: Member, channel: Union[TextChannel, int, str], creator: Member
    ) -> str:
        return NotImplemented

    @abstractmethod
    async def delete_log_entry(self, key: str) -> bool:
        return NotImplemented

    @abstractmethod
    async def edit_message(self, message_id: Union[int, str], new_content: str) -> None:
        return NotImplemented

    @abstractmethod
    async def delete_message(self, message_id: Union[int, str]) -> None:
        return NotImplemented

    @abstractmethod
    async def append_log(
        self,
        message: Message,
        *,
        message_id: str = None,
        channel_id: str = None,
        type_: str = "thread_message",
    ) -> None:
        return NotImplemented

    @abstractmethod
    async def close_log(
        self, channel_id: Union[int, str], close_message: str, closer: Member
    ) -> dict:
        return NotImplemented

    @abstractmethod
    async def search_closed_by(self, user_id: Union[int, str]) -> list:
        return NotImplemented

    @abstractmethod
    async def search_by_text(self, text: str, limit: int = 0) -> list:
        return NotImplemented

    @abstractmethod
    async def search_by_responded(self, user_id: Union[str, int], limit: int = 0) -> list:
        return NotImplemented

    @abstractmethod
    async def get_plugin_client(self, cog) -> "PluginClient":
        return NotImplemented

    @abstractmethod
    async def delete_plugin_client(self, cog):
        return NotImplemented


class PluginClient(ABC):
    @abstractmethod
    async def get(self, key: str, default=None):
        return NotImplemented

    @abstractmethod
    async def set(self, key: str, value):
        return NotImplemented


class SQLClient(ApiClient):
    def __init__(self, bot, connection_uri: DatabaseURL):
        try:
            db = Database(connection_uri)
            if connection_uri.dialect == "mysql":
                connection_uri = connection_uri.replace(driver="pymysql")
            self.engine = create_engine(str(connection_uri))
        except Exception as e:
            logger.critical("Invalid connection URI:")
            logger.critical(e)
            sys.exit(0)
        self.User = models.UserSQLModel
        self.Log = models.LogSQLModel
        self.Attachment = models.AttachmentSQLModel
        self.Config = models.ConfigSQLModel
        self.Message = models.MessageSQLModel
        super().__init__(bot, connection_uri, db)

    async def connect(self) -> None:
        ini_file = path.join(path.dirname(path.dirname(path.abspath(__file__))), "alembic.ini")
        alembic_cfg = Config(ini_file)
        command.upgrade(alembic_cfg, "head")
        await self.db.connect()

    async def disconnect(self) -> None:
        await self.db.disconnect()

    async def get_config(self) -> dict:
        query = select([self.Config]).where(self.Config.c.id == str(self.bot.user.id))
        conf = await self.db.fetch_one(query)
        if conf is None:
            query = self.Config.insert().values(id=str(self.bot.user.id))
            await self.db.execute(query)
            return {"id": str(self.bot.user.id)}
        return dict(conf.items())

    async def update_config(self, data: dict) -> None:
        toset = self.bot.config.filter_valid(data)
        toset.update(
            self.bot.config.filter_valid(
                {k: None for k in self.bot.config.all_keys if k not in data}
            )
        )
        query = (
            self.Config.update().where(self.Config.c.id == str(self.bot.user.id)).values(**toset)
        )
        await self.db.execute(query)

    async def get_or_create_user_model(self, user: Member):
        base_user_model = {
            "id": str(user.id),
            "name": user.name,
            "discriminator": user.discriminator,
            "avatar_url": str(user.avatar_url),
        }
        query = select([self.User]).where(self.User.c.id == str(user.id))
        user_model = await self.db.fetch_one(query)
        if user_model is None:
            query = self.User.insert().values(**base_user_model)
            await self.db.execute(query)
        else:
            user_model = dict(user_model.items())
            to_update = {k: v for k, v in base_user_model.items() if user_model.get(k) != v}
            if to_update:
                query = (
                    self.User.update().where(self.User.c.id == str(user.id)).values(**to_update)
                )
                await self.db.execute(query)
        return base_user_model

    async def get_log_messages(
        self,
        *,
        log_key: str = None,
        channel_id: Union[str, int] = None,
        limit: int = 5,
        filter_types: list = None,
    ) -> list:
        j = self.Log.outerjoin(self.Message, self.Log.c.key == self.Message.c.log_key)
        query = select([self.Message]).select_from(j)
        if log_key:
            clauses = [self.Log.c.key == log_key, self.Log.c.bot_id == str(self.bot.user.id)]
        else:
            clauses = [
                self.Log.c.channel_id == str(channel_id),
                self.Log.c.bot_id == str(self.bot.user.id),
            ]

        if filter_types is not None:
            clauses += [self.Message.c.type.in_(tuple(filter_types))]

        query = query.where(and_(*clauses))
        if limit > 0:
            query = query.limit(limit)
        return [dict(l.items()) for l in await self.db.fetch_all(query)]

    async def get_log_recipient(
        self, *, log_key: str = None, channel_id: Union[str, int] = None
    ) -> dict:
        j = self.Log.outerjoin(self.User, self.Log.c.recipient_id == self.User.c.id, full=True)
        query = select([self.Log.c.key, self.User]).select_from(j)
        if log_key:
            query = query.where(
                and_(self.Log.c.key == log_key, self.Log.c.bot_id == str(self.bot.user.id))
            )
        else:
            query = query.where(
                and_(
                    self.Log.c.channel_id == str(channel_id),
                    self.Log.c.bot_id == str(self.bot.user.id),
                )
            )
        return dict((await self.db.fetch_one(query)).items())

    async def get_log_creator(
        self, *, log_key: str = None, channel_id: Union[str, int] = None
    ) -> dict:
        j = self.Log.outerjoin(self.User, self.Log.c.creator_id == self.User.c.id, full=True)
        query = select([self.Log.c.key, self.User]).select_from(j)
        if log_key:
            query = query.where(
                and_(self.Log.c.key == log_key, self.Log.c.bot_id == str(self.bot.user.id))
            )
        else:
            query = query.where(
                and_(
                    self.Log.c.channel_id == str(channel_id),
                    self.Log.c.bot_id == str(self.bot.user.id),
                )
            )
        return dict((await self.db.fetch_one(query)).items())

    async def get_log_closer(
        self, *, log_key: str = None, channel_id: Union[str, int] = None
    ) -> Optional[dict]:
        j = self.Log.outerjoin(self.User, self.Log.c.closer_id == self.User.c.id, full=True)
        query = select([self.Log.c.key, self.User]).select_from(j)
        if log_key:
            query = query.where(
                and_(self.Log.c.key == log_key, self.Log.c.bot_id == str(self.bot.user.id))
            )
        else:
            query = query.where(
                and_(
                    self.Log.c.channel_id == str(channel_id),
                    self.Log.c.bot_id == str(self.bot.user.id),
                )
            )
        rtn = await self.db.fetch_one(query)
        if rtn is None:
            return None
        return dict(rtn.items())

    async def get_message_author(self, msg_id: Union[str, int]) -> dict:
        j = self.Message.outerjoin(
            self.User, self.Message.c.author_id == self.User.c.id, full=True
        )
        query = (
            select([self.Message.c.id, self.User])
            .select_from(j)
            .where(
                and_(
                    self.Message.c.id == str(msg_id),
                    self.Message.c.bot_id == str(self.bot.user.id),
                )
            )
        )
        return dict((await self.db.fetch_one(query)).items())

    async def get_message_attachments(self, msg_id: Union[str, int]) -> list:
        j = self.Message.outerjoin(
            self.Attachment, self.Message.c.id == self.Attachment.c.message_id
        )
        query = (
            select([self.Attachment])
            .select_from(j)
            .where(
                and_(
                    self.Message.c.id == str(msg_id),
                    self.Message.c.bot_id == str(self.bot.user.id),
                )
            )
        )
        return [dict(a.items()) for a in await self.db.fetch_all(query)]

    async def get_user_logs(self, user_id: Union[str, int], limit: int = 0) -> list:
        logger.debug("Retrieving user %s logs.", user_id)
        query = select([self.Log]).where(
            and_(
                self.Log.c.recipient_id == str(user_id), self.Log.c.bot_id == str(self.bot.user.id)
            )
        )
        if limit > 0:
            query = query.limit(limit)
        return [dict(l.items()) for l in await self.db.fetch_all(query)]

    async def get_latest_user_log(self, user_id: Union[str, int]) -> Optional[dict]:
        logger.debug("Retrieving user %s latest log.", user_id)
        query = select([self.Log.c.closed_at]).where(
            and_(
                self.Log.c.recipient_id == str(user_id),
                self.Log.c.open == False,
                ~self.Log.c.closed_at.is_(None),
                self.Log.c.bot_id == str(self.bot.user.id),
            )
        )
        query = query.order_by(self.Log.c.closed_at.desc())
        rtn = await self.db.fetch_one(query)
        if rtn is None:
            return None
        return dict(rtn.items())

    async def get_open_logs(self) -> list:
        query = select([self.Log.c.channel_id]).where(
            and_(self.Log.c.open == True, self.Log.c.bot_id == str(self.bot.user.id))
        )
        rows = await self.db.fetch_all(query)
        return [dict(r.items()) for r in rows]

    async def get_log_link(self, channel_id: Union[str, int]) -> str:
        logger.debug("Retrieving log link for channel %s.", channel_id)
        query = select([self.Log.c.key]).where(
            and_(
                self.Log.c.channel_id == str(channel_id),
                self.Log.c.bot_id == str(self.bot.user.id),
            )
        )
        key = (await self.db.fetch_one(query))["key"]
        prefix = self.bot.config["log_url_prefix"].strip("/")
        if prefix == "NONE":
            prefix = ""
        return f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{key}"

    async def create_log_entry(
        self, recipient: Member, channel: Union[TextChannel, int, str], creator: Member
    ) -> str:
        recipient_user = await self.get_or_create_user_model(recipient)
        if creator != recipient:
            creator_user = await self.get_or_create_user_model(creator)
        else:
            creator_user = recipient_user

        if isinstance(channel, (int, str)):
            channel_id = channel
            guild_id = self.bot.guild_id or -1
        else:
            channel_id = channel.id
            try:
                guild_id = channel.guild.id
            except AttributeError:
                guild_id = -1

        key = self.get_key()
        data = dict(
            key=key,
            bot_id=str(self.bot.user.id),
            created_at=datetime.utcnow(),
            channel_id=str(channel_id),
            guild_id=str(guild_id),
            recipient_id=recipient_user["id"],
            creator_id=creator_user["id"],
            creator_mod=isinstance(creator, Member),
        )
        query = self.Log.insert().values(**data)
        await self.db.execute(query)

        logger.debug("Created a log entry, key %s.", key)
        prefix = self.bot.config["log_url_prefix"].strip("/")
        if prefix == "NONE":
            prefix = ""
        return f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{key}"

    async def delete_log_entry(self, key: str) -> bool:
        query = self.Log.delete().where(
            and_(self.Log.c.key == key, self.Log.c.bot_id == str(self.bot.user.id))
        )
        await self.db.execute(query)
        return True

    async def edit_message(self, message_id: Union[int, str], new_content: str) -> None:
        query = (
            self.Message.update()
            .values(content=new_content, edited=True)
            .where(
                and_(
                    self.Message.c.id == str(message_id),
                    self.Message.c.bot_id == str(self.bot.user.id),
                )
            )
        )
        await self.db.execute(query)

    async def delete_message(self, message_id: Union[int, str]) -> None:
        query = (
            self.Message.update()
            .values(deleted=True)
            .where(
                and_(
                    self.Message.c.id == str(message_id),
                    self.Message.c.bot_id == str(self.bot.user.id),
                )
            )
        )
        await self.db.execute(query)

    async def append_log(
        self,
        message: Message,
        *,
        message_id: str = None,
        channel_id: str = None,
        type_: str = "thread_message",
    ) -> None:
        channel_id = str(channel_id or message.channel.id)
        message_id = str(message_id or message.id)

        query = select([self.Log.c.key]).where(
            and_(
                self.Log.c.channel_id == str(channel_id),
                self.Log.c.bot_id == str(self.bot.user.id),
            )
        )
        log = await self.db.fetch_one(query)
        if log is None:
            logger.warning("Thread cannot be found in database, recreating.")
            await self.create_log_entry(message.author, channel_id, message.author)
            log = await self.db.fetch_one(query)
        key = log["key"]
        author_user = await self.get_or_create_user_model(message.author)

        query = self.Message.insert().values(
            id=message_id,
            bot_id=str(self.bot.user.id),
            timestamp=message.created_at,
            author_id=author_user["id"],
            author_mod=not isinstance(message.channel, DMChannel),
            content=message.content,
            type=type_,
            log_key=key,
        )
        await self.db.execute(query)

        # TODO: use gather
        query = self.Attachment.insert()

        for attachment in message.attachments:
            await self.db.execute(
                query.values(
                    id=str(attachment.id),
                    filename=attachment.filename,
                    is_image=attachment.width is not None,
                    size=attachment.size,
                    url=attachment.url,
                    message_id=message_id,
                    sender_id=author_user["id"],
                )
            )

    async def close_log(
        self, channel_id: Union[int, str], close_message: str, closer: Member
    ) -> dict:
        query = select([self.Log.c.key]).where(
            and_(
                self.Log.c.channel_id == str(channel_id),
                self.Log.c.bot_id == str(self.bot.user.id),
            )
        )
        rtn = await self.db.fetch_one(query)
        if rtn is None:
            return None
        closer_user = await self.get_or_create_user_model(closer)
        query = (
            self.Log.update()
            .values(
                open=False,
                closed_at=datetime.utcnow(),
                closer_id=closer_user["id"],
                close_message=close_message,
            )
            .where(and_(self.Log.c.key == rtn["key"], self.Log.c.bot_id == str(self.bot.user.id)))
        )
        await self.db.execute(query)
        return dict(rtn.items())

    async def search_closed_by(self, user_id: Union[int, str]) -> list:
        query = select([self.Log]).where(
            and_(
                self.Log.c.closer_id == str(user_id),
                self.Log.c.open == False,
                self.Log.c.bot_id == str(self.bot.user.id),
            )
        )
        query = query.order_by(self.Log.c.created_at)
        return [dict(l.items()) for l in await self.db.fetch_all(query)]

    async def search_by_text(self, text: str, limit: int = 0) -> list:
        j = self.Message.outerjoin(self.Log, self.Message.c.log_key == self.Log.c.key, full=True)
        query = (
            select([self.Message.c.id, self.Log])
            .select_from(j)
            .where(
                and_(
                    self.Message.c.content.ilike(f"%{text}%"),
                    self.Log.c.bot_id == str(self.bot.user.id),
                )
            )
        )
        if limit > 0:
            query = query.limit(limit)
        return [dict(l.items()) for l in await self.db.fetch_all(query)]

    async def search_by_responded(self, user_id: Union[str, int], limit: int = 0) -> list:
        j = self.Message.outerjoin(self.Log, self.Message.c.log_key == self.Log.c.key, full=True)
        query = (
            select([self.Message.c.id, self.Log])
            .select_from(j)
            .where(
                and_(
                    self.Message.c.author_id == str(user_id),
                    self.Message.c.author_mod == True,
                    self.Message.c.type.in_(("anonymous", "thread_message")),
                    self.Log.c.bot_id == str(self.bot.user.id),
                )
            )
        )
        if limit > 0:
            query = query.limit(limit)
        return [dict(l.items()) for l in await self.db.fetch_all(query)]

    async def get_plugin_client(self, cog) -> PluginClient:
        plugin_name = f"plugin_{cog.__class__.__name__}"
        PluginSQLModel = Table(
            plugin_name,
            models.metadata,
            Column("key", String(250), primary_key=True),
            Column("value", Text, nullable=True),
        )
        Index(f"idx_{plugin_name}", PluginSQLModel.c.key)
        self.engine.create(PluginSQLModel, checkfirst=True)
        return SQLPluginClient(PluginSQLModel, self.db)

    async def delete_plugin_client(self, cog):
        plugin_name = f"plugin_{cog.__class__.__name__}"
        self.engine.execute(f"DROP TABLE {plugin_name}", checkfirst=True)


class SQLPluginClient(PluginClient):
    def __init__(self, plugin_model, db):
        self.Plugin = plugin_model
        self.db = db

    async def get(self, key: str, default=None):
        query = select([self.Plugin]).where(self.Plugin.c.key == key)
        val = await self.db.fetch_one(query)
        if val is None:
            return default
        return ujson.loads(val["value"])

    async def set(self, key: str, value):
        query = select([self.Plugin]).where(self.Plugin.c.key == key)
        val = await self.db.fetch_one(query)
        if val is not None:
            query = (
                self.Plugin.update()
                .where(self.Plugin.c.key == key)
                .values(value=ujson.dumps(value))
            )
        else:
            query = self.Plugin.insert().values(key=key, value=ujson.dumps(value))
        await self.db.execute(query)


class MongoDBClient(ApiClient):
    def __init__(self, bot, connection_uri):
        mongo_uri = str(connection_uri)
        try:
            db = AsyncIOMotorClient(mongo_uri).get_default_database("modmail_bot")
            if db.name != "modmail_bot":
                logger.warning(
                    "A default database name has been provided. "
                    "If you been using this bot for a while and noticed your "
                    "data missing, change your connection_uri/mongo_uri to "
                    '"mongodb+srv://[...].mongodb.net/modmail_bot" to use '
                    "the former preset modmail_bot database."
                )
        except ConfigurationError as e:
            if "The DNS operation timed out" in str(e):
                logger.critical(
                    "Failed to connect to database due to DNS resolve timeout, "
                    "check your internet connection and DNS resolvers settings."
                )
            else:
                logger.critical(
                    "Your MONGO_URI might be copied wrong, try re-copying from the source again. "
                    "Otherwise noted in the following message:"
                )
            logger.critical("Error: ", exc_info=True)
            sys.exit(0)

        self.instance = Instance(db)
        self.Log = self.instance.register(models.LogMongoModel)
        self.Message = self.instance.register(models.MessageMongoModel)
        self.User = self.instance.register(models.UserMongoModel)
        self.Attachment = self.instance.register(models.AttachmentMongoModel)
        self.Config = self.instance.register(models.ConfigMongoModel)
        self.bot_ref = None
        super().__init__(bot, mongo_uri, db)

    async def connect(self) -> None:
        try:
            await self.db.client.server_info()
        except Exception as exc:
            logger.critical("Something went wrong while connecting to the database.")
            message = f"{type(exc).__name__}: {str(exc)}"
            logger.critical(message)

            if "ServerSelectionTimeoutError" in message:
                if 'No replica set members match selector "Primary()"' in message:
                    logger.critical(
                        "Failed to connect to the database, likely caused by your or the server's "
                        "internet connection. Try again later to see if the problem resolves."
                    )
                else:
                    logger.critical(
                        "This may have been caused by not whitelisting "
                        "IPs correctly. Make sure to whitelist all "
                        "IPs (0.0.0.0/0) https://i.imgur.com/mILuQ5U.png"
                    )
            if "OperationFailure" in message:
                logger.critical(
                    "This is due to having invalid credentials in your MONGO_URI. "
                    "Remember you need to substitute `<password>` with your actual password."
                )
                logger.critical(
                    "Be sure to URL encode your username and password (not the entire URL!!), "
                    "https://www.urlencoder.io/, if this issue persists, try changing your username and password "
                    "to only include alphanumeric characters, no symbols."
                    ""
                )

            raise
        else:
            logger.debug("Successfully connected to the database.")
        logger.line("debug")

        migrated = await self.migrate()
        if not migrated:
            await self.Log.ensure_indexes()
            await self.Message.ensure_indexes()
            await self.User.ensure_indexes()
            await self.Attachment.ensure_indexes()
            await self.Config.ensure_indexes()

    async def disconnect(self) -> None:
        pass

    async def do_migration(self, s):

        logger.warning("-----------------------")
        logger.warning("  Migrating database   ")
        logger.warning("(this may take a while)")
        logger.warning("-----------------------")

        serialize = {
            "oauth_whitelist",
            "blocked",
            "blocked_whitelist",
            "command_permissions",
            "level_permissions",
            "override_command_level",
            "snippets",
            "notification_squad",
            "subscriptions",
            "closures",
            "plugins",
            "aliases",
        }
        ids = {
            "main_category_id",
            "log_channel_id",
            "fallback_category_id",
            "guild_id",
            "modmail_guild_id",
        }

        this_bot = None
        bots = {}
        logger.info("Migrating config models")

        async for conf in self.db.config_migrate.find({}):
            try:
                for x in serialize:
                    if x in conf:
                        conf[x] = ujson.dumps(conf[x])
                for x in ids:
                    if isinstance(conf.get(x), int):
                        conf[x] = str(conf[x])

                conf["id"] = str(conf["bot_id"])
                conf.pop("bot_id", None)
                conf.pop("_id", None)
                result = await self.db.config.insert_one(conf, session=s)
                bots[conf["id"]] = result.inserted_id
                if this_bot is None or conf["id"] == str(self.bot.user.id):
                    this_bot = result.inserted_id
            except Exception as e:
                logger.error("Failed to migrate config %s: %s", conf, e)
                if "dup key" in str(e):
                    continue
                if isinstance(e, KeyError):
                    continue
                if not self.bot.config["force_migrate"]:
                    raise
                continue

        total_logs = await self.db.logs_migrate.count_documents({})
        subdivisions = 200
        totaldivisions = total_logs // subdivisions
        added_users = {}
        logger.info("Creating users models")
        for i in range(0, totaldivisions + 1):
            logger.info("Migrating users %d/%d", i + 1, totaldivisions + 1)
            async for log in self.db.logs_migrate.find(
                {}, projection=["key", "creator", "recipient", "closer", "messages.author"]
            ).sort("created_at", -1).skip(i * subdivisions).limit(subdivisions):
                try:
                    # logger.debug("migrating users for log: %s", log["key"])
                    if log.get("closer") and str(log["closer"]["id"]) not in added_users:
                        result = await self.db.logs_user.insert_one(
                            dict(
                                id=str(log["closer"]["id"]),
                                name=log["closer"]["name"],
                                discriminator=log["closer"]["discriminator"],
                                avatar_url=log["closer"]["avatar_url"],
                            ),
                            session=s,
                        )
                        added_users[str(log["closer"]["id"])] = result.inserted_id

                    for msg in reversed(log["messages"]):
                        if str(msg["author"]["id"]) not in added_users:
                            result = await self.db.logs_user.insert_one(
                                dict(
                                    id=str(msg["author"]["id"]),
                                    name=msg["author"]["name"],
                                    discriminator=msg["author"]["discriminator"],
                                    avatar_url=msg["author"]["avatar_url"],
                                ),
                                session=s,
                            )
                            added_users[str(msg["author"]["id"])] = result.inserted_id

                    if str(log["recipient"]["id"]) not in added_users:
                        result = await self.db.logs_user.insert_one(
                            dict(
                                id=str(log["recipient"]["id"]),
                                name=log["recipient"]["name"],
                                discriminator=log["recipient"]["discriminator"],
                                avatar_url=log["recipient"]["avatar_url"],
                            ),
                            session=s,
                        )
                        added_users[str(log["recipient"]["id"])] = result.inserted_id

                    if str(log["creator"]["id"]) not in added_users:
                        result = await self.db.logs_user.insert_one(
                            dict(
                                id=str(log["creator"]["id"]),
                                name=log["creator"]["name"],
                                discriminator=log["creator"]["discriminator"],
                                avatar_url=log["creator"]["avatar_url"],
                            ),
                            session=s,
                        )
                        added_users[str(log["creator"]["id"])] = result.inserted_id
                except Exception as e:
                    logger.error("Failed to migrate users for log %s: %s", log, e)
                    if "dup key" in str(e):
                        continue
                    if isinstance(e, KeyError):
                        continue
                    if not self.bot.config["force_migrate"]:
                        raise
                    continue

        logger.info("Migrating log models")
        for i in range(0, totaldivisions + 1):  # To prevent cursor timeout
            logger.info("Migrating logs %d/%d", i + 1, totaldivisions + 1)
            async for log in self.db.logs_migrate.find(
                {},
                projection=[
                    "key",
                    "created_at",
                    "closed_at",
                    "open",
                    "bot_id",
                    "creator.mod",
                    "creator.id",
                    "channel_id",
                    "guild_id",
                    "recipient.id",
                    "closer.id",
                    "close_message",
                    "messages.timestamp",
                    "messages.message_id",
                    "messages.author.id",
                    "messages.author.mod",
                    "messages.content",
                    "messages.type",
                    "messages.edited",
                    "messages.deleted",
                    "messages.attachments",
                ],
            ).sort("created_at", 1).skip(i * subdivisions).limit(subdivisions):
                try:
                    # logger.debug("migrating log: %s", log["key"])
                    created_at = datetime.fromisoformat(log["created_at"])
                    closed_at = (
                        datetime.fromisoformat(log["closed_at"]) if log.get("closed_at") else None
                    )
                    creator_mod = log["creator"]["mod"]
                    bot = bots.get(log.get("bot_id")) or this_bot
                    log_result = await self.db.logs.insert_one(
                        dict(
                            key=log["key"],
                            bot=bot,
                            open=log["open"],
                            created_at=created_at,
                            closed_at=closed_at,
                            channel_id=str(log["channel_id"]),
                            guild_id=str(log["guild_id"]),
                            recipient=added_users[str(log["recipient"]["id"])],
                            creator=added_users[str(log["creator"]["id"])],
                            creator_mod=creator_mod,
                            closer=added_users[str(log["closer"]["id"])]
                            if log.get("closer")
                            else None,
                            close_message=log.get("close_message"),
                        ),
                        session=s,
                    )
                    messages = log["messages"]
                except Exception as e:
                    logger.error("Failed to migrate log %s: %s", log, e)
                    if "dup key" in str(e):
                        continue
                    if isinstance(e, KeyError):
                        continue
                    if not self.bot.config["force_migrate"]:
                        raise
                    continue

                for msg in messages:
                    try:
                        timestamp = datetime.fromisoformat(msg["timestamp"])
                        message_result = await self.db.logs_message.insert_one(
                            dict(
                                id=str(msg["message_id"]),
                                bot=bot,
                                timestamp=timestamp,
                                author=added_users[str(msg["author"]["id"])],
                                author_mod=msg["author"]["mod"],
                                content=msg["content"],
                                type=msg.get("type") or "thread_message",
                                edited=msg.get("edited", False),
                                deleted=msg.get("deleted", False),
                                log=log_result.inserted_id,
                            ),
                            session=s,
                        )
                        for i, att in enumerate(msg["attachments"]):
                            if isinstance(att, str):
                                att = {"url": att}
                            att_id = str(att.get("id"))
                            if len(att_id) < 16:
                                att_id = f'{msg["message_id"]}_{i}'
                            await self.db.logs_attachment.insert_one(
                                dict(
                                    id=att_id,
                                    filename=str(att.get("filename", "attachment")),
                                    url=att["url"],
                                    is_image=bool(att.get("is_image", True)),
                                    size=att.get("size") or -1,
                                    message=message_result.inserted_id,
                                    sender=added_users[str(msg["author"]["id"])],
                                ),
                                session=s,
                            )
                    except Exception as e:
                        logger.error("Failed to migrate message %s: %s", msg, e)
                        if "dup key" in str(e):
                            continue
                        if isinstance(e, KeyError):
                            continue
                        if not self.bot.config["force_migrate"]:
                            raise
                        continue

        await self.db.db_version.update_one({"_id": "bot"}, {"$set": {"version": 2}}, session=s)

        logger.warning("------------------------------")
        logger.warning("Successfully migrated database")
        logger.warning("------------------------------")

    async def migrate(self) -> bool:
        v = await self.db.db_version.find_one({"_id": "bot"})
        if v is None:
            v = {"_id": "bot", "version": 1}
            await self.db.db_version.insert_one(v)

        if v["version"] == 2:
            return False
        if v["version"] != 1:
            raise ValidationError("Database version is not 1 or 2.")

        if not await self.db.config.find_one({}):
            await self.db.db_version.update_one({"_id": "bot"}, {"$set": {"version": 2}})
            return  # no config, new database probably

        if not await self.db.config_migrate.find_one({}):
            await self.db.config.rename("config_migrate")
        if not await self.db.logs_migrate.find_one({}):
            await self.db.logs.rename("logs_migrate")

        await self.db.logs_migrate.create_index([("created_at", -1)])

        await self.db.config.drop()
        await self.db.logs.drop()
        await self.db.logs_user.drop()
        await self.db.logs_attachment.drop()
        await self.db.logs_message.drop()
        await self.Log.ensure_indexes()
        await self.Message.ensure_indexes()
        await self.User.ensure_indexes()
        await self.Attachment.ensure_indexes()
        await self.Config.ensure_indexes()

        logger.info("Removing duplicate logs")
        async for doc in self.db.logs_migrate.aggregate(
            [
                {
                    "$group": {
                        "_id": {"channel_id": "$channel_id"},
                        "dups": {"$push": "$_id"},
                        "count": {"$sum": 1},
                    }
                },
                {"$match": {"count": {"$gt": 1}}},
            ]
        ):
            dups = list(doc["dups"][1:])
            result = await self.db.logs_migrate.delete_many({"_id": {"$in": dups}})
            logger.debug("Removed dupe %s, total %s", dups[0], result.deleted_count)

        try:
            await self.db.client.admin.command(
                "setParameter", {"transactionLifetimeLimitSeconds": 1800}
            )
            logger.debug("Successfully set transactionLifetimeLimitSeconds")
        except OperationFailure as e:
            logger.error(
                "MongoDB user lacks admin permissions, cannot change timeout. "
                "If the migration fails, grant the MongoDB user admin permission or set "
                "FORCE_MIGRATE=true (unsafe, may cause data loss)."
            )
            logger.error(str(e))

        try:
            if self.bot.config["force_migrate"]:
                logger.warning(
                    "Starting force migrate mode, if the migration fails, you may need to remake a new database."
                )
                await self.do_migration(None)
            else:
                async with await self.db.client.start_session() as s:
                    await s.with_transaction(self.do_migration)
        except Exception:
            logger.critical("Failed to migrate database", exc_info=True)
            try:
                if await self.db.config_migrate.find_one({}):
                    await self.db.config.drop()
                    await self.db.config_migrate.rename("config")
            except Exception:
                logger.warning("Failed to rename config_migrate back to config", exc_info=True)
            try:
                if await self.db.logs_migrate.find_one({}):
                    await self.db.logs.drop()
                    await self.db.logs_migrate.rename("logs")
            except Exception:
                logger.warning("Failed to rename logs_migrate back to logs", exc_info=True)
            sys.exit(0)
        return True

    async def get_config(self) -> dict:
        conf = await self.Config.find_one({"id": str(self.bot.user.id)})
        if conf is None:
            logger.debug("Creating a new config entry for bot %s.", self.bot.user.id)
            conf = self.Config(id=str(self.bot.user.id))
            await conf.commit()
        self.bot_ref = fields.Reference(self.Config, conf.pk)
        return dict(conf.items())

    async def update_config(self, data: dict) -> None:
        toset = self.bot.config.filter_valid(data)
        toset.update(
            self.bot.config.filter_valid(
                {k: None for k in self.bot.config.all_keys if k not in data}
            )
        )
        conf = await self.Config.find_one({"id": str(self.bot.user.id)})
        if conf is None:
            conf = self.Config(id=str(self.bot.user.id))
        for k, v in toset.items():
            setattr(conf, k, v)
        await conf.commit()

    async def get_or_create_user_model(self, user: Member):
        user_model = await self.User.find_one({"id": str(user.id)})
        if user_model is None:
            user_model = self.User(id=str(user.id))
        user_model.name = user.name
        user_model.discriminator = user.discriminator
        user_model.avatar_url = str(user.avatar_url)
        await user_model.commit()
        return user_model

    async def get_log_messages(
        self,
        *,
        log_key: str = None,
        channel_id: Union[str, int] = None,
        limit: int = 5,
        filter_types: list = None,
    ) -> list:
        if log_key:
            log = await self.Log.find_one({"key": log_key, "bot": self.bot_ref.pk})
        else:
            log = await self.Log.find_one({"channel_id": str(channel_id), "bot": self.bot_ref.pk})

        query = {"log": log.pk, "bot": self.bot_ref.pk}
        if filter_types is not None:
            query["type"] = {"$in": filter_types}
        cur = self.Message.find(query)
        if limit > 0:
            cur.limit(limit)
        return [dict(l.items()) for l in await cur.to_list(None)]

    async def get_log_recipient(
        self, *, log_key: str = None, channel_id: Union[str, int] = None
    ) -> dict:
        if log_key:
            log = await self.Log.find_one({"key": log_key, "bot": self.bot_ref.pk})
        else:
            log = await self.Log.find_one({"channel_id": str(channel_id), "bot": self.bot_ref.pk})

        return dict((await self.User.find_one({"_id": log.recipient.pk})).items())

    async def get_log_creator(
        self, *, log_key: str = None, channel_id: Union[str, int] = None
    ) -> dict:
        if log_key:
            log = await self.Log.find_one({"key": log_key, "bot": self.bot_ref.pk})
        else:
            log = await self.Log.find_one({"channel_id": str(channel_id), "bot": self.bot_ref.pk})

        return dict((await self.User.find_one({"_id": log.creator.pk})).items())

    async def get_log_closer(
        self, *, log_key: str = None, channel_id: Union[str, int] = None
    ) -> Optional[dict]:
        if log_key:
            log = await self.Log.find_one({"key": log_key, "bot": self.bot_ref.pk})
        else:
            log = await self.Log.find_one({"channel_id": str(channel_id), "bot": self.bot_ref.pk})

        if not log.closer:
            return None
        return dict((await self.User.find_one({"_id": log.closer.pk})).items())

    async def get_message_author(self, msg_id: Union[str, int]) -> dict:
        msg = await self.Message.find_one({"id": str(msg_id), "bot": self.bot_ref.pk})
        return dict((await self.User.find_one({"_id": msg.author.pk})).items())

    async def get_message_attachments(self, msg_id: Union[str, int]) -> list:
        msg = await self.Message.find_one({"id": str(msg_id), "bot": self.bot_ref.pk})
        return [
            dict(a.items()) for a in await self.Attachment.find({"message": msg.pk}).to_list(None)
        ]

    async def get_user_logs(self, user_id: Union[str, int], limit: int = 0) -> list:
        user_model = await self.User.find_one({"id": str(user_id)})
        if user_model is None:
            return []
        logger.debug("Retrieving user %s logs.", user_id)
        cur = self.Log.find({"recipient": user_model.pk, "bot": self.bot_ref.pk})
        if limit > 0:
            cur.limit(limit)
        return [dict(l.items()) for l in await cur.to_list(None)]

    async def get_latest_user_log(self, user_id: Union[str, int]) -> Optional[dict]:
        user_model = await self.User.find_one({"id": str(user_id)})
        if user_model is None:
            return None

        logger.debug("Retrieving user %s latest log.", user_id)
        query = {"recipient": user_model.pk, "bot": self.bot_ref.pk, "open": False}
        return dict((await self.Log.find_one(query, sort=[("closed_at", -1)])).items())

    async def get_open_logs(self) -> list:
        return [
            dict(l.items())
            for l in await self.Log.find({"open": True, "bot": self.bot_ref.pk}).to_list(None)
        ]

    async def get_log_link(self, channel_id: Union[str, int]) -> str:
        logger.debug("Retrieving log link for channel %s.", channel_id)

        doc = await self.Log.find_one({"channel_id": str(channel_id), "bot": self.bot_ref.pk})
        prefix = self.bot.config["log_url_prefix"].strip("/")
        if prefix == "NONE":
            prefix = ""
        return (
            f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{doc['key']}"
        )

    async def create_log_entry(
        self, recipient: Member, channel: Union[TextChannel, int, str], creator: Member
    ) -> str:

        recipient_user = await self.get_or_create_user_model(recipient)
        if creator != recipient:
            creator_user = await self.get_or_create_user_model(creator)
        else:
            creator_user = recipient_user

        if isinstance(channel, (int, str)):
            channel_id = channel
            guild_id = self.bot.guild_id or -1
        else:
            channel_id = channel.id
            try:
                guild_id = channel.guild.id
            except AttributeError:
                guild_id = -1

        for _ in range(3):
            key = self.get_key()
            log = self.Log(
                key=key,
                bot=self.bot_ref,
                created_at=datetime.utcnow(),
                channel_id=str(channel_id),
                guild_id=str(guild_id),
                recipient=recipient_user,
                creator=creator_user,
                creator_mod=isinstance(creator, Member),
            )
            try:
                await log.commit()
            except ValidationError as e:
                if "{'key': 'Field value must be unique.'}" in str(e):
                    logger.debug("Dupe key %s, trying again.", key)
                    continue
                raise
            break
        else:
            raise ValidationError("Cannot create a log entry.")

        logger.debug("Created a log entry, key %s.", key)
        prefix = self.bot.config["log_url_prefix"].strip("/")
        if prefix == "NONE":
            prefix = ""
        return f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{key}"

    async def delete_log_entry(self, key: str) -> bool:
        log = await self.Log.find_one({"key": key, "bot": self.bot_ref.pk})
        if log is None:
            return False
        for m in await self.Message.find({"log": log.pk, "bot": self.bot_ref.pk}).to_list(None):
            for a in await self.Attachment.find({"message": m.pk}).to_list(None):
                await a.delete()
            await m.delete()
        await log.delete()
        return True

    async def edit_message(self, message_id: Union[int, str], new_content: str) -> None:
        msg = await self.Message.find_one({"id": str(message_id), "bot": self.bot_ref.pk})
        msg.content = new_content
        msg.edited = True
        await msg.commit()

    async def delete_message(self, message_id: Union[int, str]) -> None:
        msg = await self.Message.find_one({"id": str(message_id), "bot": self.bot_ref.pk})
        msg.deleted = True
        await msg.commit()

    async def append_log(
        self,
        message: Message,
        *,
        message_id: str = None,
        channel_id: str = None,
        type_: str = "thread_message",
    ) -> None:
        channel_id = str(channel_id or message.channel.id)
        message_id = str(message_id or message.id)

        log = await self.Log.find_one({"channel_id": channel_id, "bot": self.bot_ref.pk})
        if log is None:
            logger.warning("Thread cannot be found in database, recreating.")
            await self.create_log_entry(message.author, channel_id, message.author)
            log = await self.Log.find_one({"channel_id": channel_id, "bot": self.bot_ref.pk})
        author_user = await self.get_or_create_user_model(message.author)

        msg = self.Message(
            id=message_id,
            bot=self.bot_ref,
            timestamp=message.created_at,
            author=author_user,
            author_mod=not isinstance(message.channel, DMChannel),
            content=message.content,
            type=type_,
            log=log,
        )
        await msg.commit()

        # TODO: use gather
        for attachment in message.attachments:
            att = self.Attachment(
                id=str(attachment.id),
                filename=attachment.filename,
                is_image=attachment.width is not None,
                size=attachment.size,
                url=attachment.url,
                message=msg,
                sender=author_user,
            )
            await att.commit()

    async def close_log(
        self, channel_id: Union[int, str], close_message: str, closer: Member
    ) -> dict:
        log = await self.Log.find_one({"channel_id": str(channel_id), "bot": self.bot_ref.pk})
        if log is None:
            return None
        closer_user = await self.get_or_create_user_model(closer)
        log.open = False
        log.closed_at = datetime.utcnow()
        log.closer = closer_user.pk
        log.close_message = close_message
        await log.commit()
        return dict(log.items())

    async def search_closed_by(self, user_id: Union[int, str]) -> list:
        closer = await self.User.find_one({"id": str(user_id)})
        if closer is None:
            return []
        cur = self.Log.find({"open": False, "closer": closer.pk, "bot": self.bot_ref.pk}).sort(
            "created_at"
        )
        return [dict(l.items()) for l in await cur.to_list(None)]

    async def search_by_text(self, text: str, limit: int = 0) -> list:
        cur = self.Message.find({"bot": self.bot_ref.pk, "$text": {"$search": f'"{text}"'},},)
        if limit > 0:
            cur.limit(limit)
        logs = []
        for m in await cur.to_list(None):
            log = await self.Log.find_one({"_id": m.log.pk, "bot": self.bot_ref.pk})
            if log:
                logs += [dict(log.items())]
        return logs

    async def search_by_responded(self, user_id: Union[str, int], limit: int = 0) -> list:
        user_model = await self.User.find_one({"id": str(user_id)})
        if user_model is None:
            return []

        cur = self.Message.find(
            {
                "author": user_model.pk,
                "type": {"$in": ["anonymous", "thread_message"]},
                "author_mod": True,
                "bot": self.bot_ref.pk,
            }
        )
        if limit > 0:
            cur.limit(limit)

        logs = []
        for m in await cur.to_list(None):
            log = await self.Log.find_one({"_id": m.log.pk, "bot": self.bot_ref.pk})
            if log:
                logs += [dict(log.items())]
        return logs

    async def get_plugin_client(self, cog) -> PluginClient:
        plugin_name = f"plugin_{cog.__class__.__name__}"

        class Meta:
            collection_name = plugin_name

        Plugin = type(
            plugin_name,
            (Document,),
            {
                "Meta": Meta,
                "key": fields.StringField(
                    validate=validate.Length(max=250), unique=True, required=True
                ),
                "value": fields.StringField(required=True, allow_none=True),
            },
        )
        Plugin = self.instance.register(Plugin)
        await Plugin.ensure_indexes()
        return MongoPluginClient(Plugin)

    async def delete_plugin_client(self, cog):
        plugin_name = f"plugin_{cog.__class__.__name__}"
        await self.db[plugin_name].drop()


class MongoPluginClient(PluginClient):
    def __init__(self, plugin_model):
        self.Plugin = plugin_model

    async def get(self, key: str, default=None):
        val = await self.Plugin.find_one({"key": key})
        if val is None:
            return default
        return ujson.loads(val.value)

    async def set(self, key: str, value):
        val = await self.Plugin.find_one({"key": key})
        if val is None:
            val = self.Plugin(key=key)
        val.value = ujson.dumps(value)
        await val.commit()
