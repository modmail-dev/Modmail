import secrets
import sys
from datetime import datetime
from json import JSONDecodeError
from typing import Union, Optional

from discord import Member, DMChannel, TextChannel, Message

from aiohttp import ClientResponseError, ClientResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConfigurationError

from core.models import getLogger

logger = getLogger(__name__)


class ApiClient:
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
    session : ClientSession
        The bot's current running `ClientSession`.
    """

    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.session = bot.session

    async def request(
        self,
        url: str,
        method: str = "GET",
        payload: dict = None,
        return_response: bool = False,
        headers: dict = None,
    ) -> Union[ClientResponse, dict, str]:
        """
        Makes a HTTP request.

        Parameters
        ----------
        url : str
            The destination URL of the request.
        method : str
            The HTTP method (POST, GET, PUT, DELETE, FETCH, etc.).
        payload : Dict[str, Any]
            The json payload to be sent along the request.
        return_response : bool
            Whether the `ClientResponse` object should be returned.
        headers : Dict[str, str]
            Additional headers to `headers`.

        Returns
        -------
        ClientResponse or Dict[str, Any] or List[Any] or str
            `ClientResponse` if `return_response` is `True`.
            `dict` if the returned data is a json object.
            `list` if the returned data is a json list.
            `str` if the returned data is not a valid json data,
            the raw response.
        """
        async with self.session.request(method, url, headers=headers, json=payload) as resp:
            if return_response:
                return resp
            try:
                return await resp.json()
            except (JSONDecodeError, ClientResponseError):
                return await resp.text()

    @property
    def logs(self):
        return self.db.logs

    async def setup_indexes(self):
        return NotImplemented

    async def validate_database_connection(self):
        return NotImplemented

    async def get_user_logs(self, user_id: Union[str, int]) -> list:
        return NotImplemented

    async def get_latest_user_logs(self, user_id: Union[str, int]):
        return NotImplemented

    async def get_responded_logs(self, user_id: Union[str, int]) -> list:
        return NotImplemented

    async def get_open_logs(self) -> list:
        return NotImplemented

    async def get_log(self, channel_id: Union[str, int]) -> dict:
        return NotImplemented

    async def get_log_link(self, channel_id: Union[str, int]) -> str:
        return NotImplemented

    async def create_log_entry(
        self, recipient: Member, channel: TextChannel, creator: Member
    ) -> str:
        return NotImplemented

    async def delete_log_entry(self, key: str) -> bool:
        return NotImplemented

    async def get_config(self) -> dict:
        return NotImplemented

    async def update_config(self, data: dict):
        return NotImplemented

    async def edit_message(self, message_id: Union[int, str], new_content: str) -> None:
        return NotImplemented

    async def append_log(
        self,
        message: Message,
        *,
        message_id: str = "",
        channel_id: str = "",
        type_: str = "thread_message",
    ) -> dict:
        return NotImplemented

    async def post_log(self, channel_id: Union[int, str], data: dict) -> dict:
        return NotImplemented

    async def search_closed_by(self, user_id: Union[int, str]):
        return NotImplemented

    async def search_by_text(self, text: str, limit: Optional[int]):
        return NotImplemented

    def get_plugin_partition(self, cog):
        return NotImplemented


class MongoDBClient(ApiClient):
    def __init__(self, bot):
        mongo_uri = bot.config["connection_uri"]
        if mongo_uri is None:
            mongo_uri = bot.config["mongo_uri"]
            if mongo_uri is not None:
                logger.warning(
                    "You're using the old config MONGO_URI, "
                    "consider switching to the new CONNECTION_URI config."
                )
            else:
                logger.critical("A Mongo URI is necessary for the bot to function.")
                raise RuntimeError

        try:
            db = AsyncIOMotorClient(mongo_uri).modmail_bot
        except ConfigurationError as e:
            logger.critical(
                "Your MONGO_URI might be copied wrong, try re-copying from the source again. "
                "Otherwise noted in the following message:"
            )
            logger.critical(e)
            sys.exit(0)

        super().__init__(bot, db)

    async def setup_indexes(self):
        """Setup text indexes so we can use the $search operator"""
        coll = self.db.logs
        index_name = "messages.content_text_messages.author.name_text_key_text"

        index_info = await coll.index_information()

        # Backwards compatibility
        old_index = "messages.content_text_messages.author.name_text"
        if old_index in index_info:
            logger.info("Dropping old index: %s", old_index)
            await coll.drop_index(old_index)

        if index_name not in index_info:
            logger.info('Creating "text" index for logs collection.')
            logger.info("Name: %s", index_name)
            await coll.create_index(
                [("messages.content", "text"), ("messages.author.name", "text"), ("key", "text")]
            )
        logger.debug("Successfully configured and verified database indexes.")

    async def validate_database_connection(self):
        try:
            await self.db.command("buildinfo")
        except Exception as exc:
            logger.critical("Something went wrong while connecting to the database.")
            message = f"{type(exc).__name__}: {str(exc)}"
            logger.critical(message)

            if "ServerSelectionTimeoutError" in message:
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

    async def get_user_logs(self, user_id: Union[str, int]) -> list:
        query = {"recipient.id": str(user_id), "guild_id": str(self.bot.guild_id)}
        projection = {"messages": {"$slice": 5}}
        logger.debug("Retrieving user %s logs.", user_id)

        return await self.logs.find(query, projection).to_list(None)

    async def get_latest_user_logs(self, user_id: Union[str, int]):
        query = {"recipient.id": str(user_id), "guild_id": str(self.bot.guild_id), "open": False}
        projection = {"messages": {"$slice": 5}}
        logger.debug("Retrieving user %s latest logs.", user_id)

        return await self.logs.find_one(query, projection, limit=1, sort=[("closed_at", -1)])

    async def get_responded_logs(self, user_id: Union[str, int]) -> list:
        query = {
            "open": False,
            "messages": {
                "$elemMatch": {
                    "author.id": str(user_id),
                    "author.mod": True,
                    "type": {"$in": ["anonymous", "thread_message"]},
                }
            },
        }
        return await self.logs.find(query).to_list(None)

    async def get_open_logs(self) -> list:
        query = {"open": True}
        return await self.logs.find(query).to_list(None)

    async def get_log(self, channel_id: Union[str, int]) -> dict:
        logger.debug("Retrieving channel %s logs.", channel_id)
        return await self.logs.find_one({"channel_id": str(channel_id)})

    async def get_log_link(self, channel_id: Union[str, int]) -> str:
        doc = await self.get_log(channel_id)
        logger.debug("Retrieving log link for channel %s.", channel_id)
        prefix = self.bot.config["log_url_prefix"].strip("/")
        if prefix == "NONE":
            prefix = ""
        return (
            f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{doc['key']}"
        )

    async def create_log_entry(
        self, recipient: Member, channel: TextChannel, creator: Member
    ) -> str:
        key = secrets.token_hex(6)

        await self.logs.insert_one(
            {
                "_id": key,
                "key": key,
                "open": True,
                "created_at": str(datetime.utcnow()),
                "closed_at": None,
                "channel_id": str(channel.id),
                "guild_id": str(self.bot.guild_id),
                "bot_id": str(self.bot.user.id),
                "recipient": {
                    "id": str(recipient.id),
                    "name": recipient.name,
                    "discriminator": recipient.discriminator,
                    "avatar_url": str(recipient.avatar_url),
                    "mod": False,
                },
                "creator": {
                    "id": str(creator.id),
                    "name": creator.name,
                    "discriminator": creator.discriminator,
                    "avatar_url": str(creator.avatar_url),
                    "mod": isinstance(creator, Member),
                },
                "closer": None,
                "messages": [],
            }
        )
        logger.debug("Created a log entry, key %s.", key)
        prefix = self.bot.config["log_url_prefix"].strip("/")
        if prefix == "NONE":
            prefix = ""
        return f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{key}"

    async def delete_log_entry(self, key: str) -> bool:
        result = await self.logs.delete_one({"key": key})
        return result.deleted_count == 1

    async def get_config(self) -> dict:
        conf = await self.db.config.find_one({"bot_id": self.bot.user.id})
        if conf is None:
            logger.debug("Creating a new config entry for bot %s.", self.bot.user.id)
            await self.db.config.insert_one({"bot_id": self.bot.user.id})
            return {"bot_id": self.bot.user.id}
        return conf

    async def update_config(self, data: dict):
        toset = self.bot.config.filter_valid(data)
        unset = self.bot.config.filter_valid(
            {k: 1 for k in self.bot.config.all_keys if k not in data}
        )

        if toset and unset:
            return await self.db.config.update_one(
                {"bot_id": self.bot.user.id}, {"$set": toset, "$unset": unset}
            )
        if toset:
            return await self.db.config.update_one({"bot_id": self.bot.user.id}, {"$set": toset})
        if unset:
            return await self.db.config.update_one({"bot_id": self.bot.user.id}, {"$unset": unset})

    async def edit_message(self, message_id: Union[int, str], new_content: str) -> None:
        await self.logs.update_one(
            {"messages.message_id": str(message_id)},
            {"$set": {"messages.$.content": new_content, "messages.$.edited": True}},
        )

    async def append_log(
        self,
        message: Message,
        *,
        message_id: str = "",
        channel_id: str = "",
        type_: str = "thread_message",
    ) -> dict:
        channel_id = str(channel_id) or str(message.channel.id)
        message_id = str(message_id) or str(message.id)

        data = {
            "timestamp": str(message.created_at),
            "message_id": message_id,
            "author": {
                "id": str(message.author.id),
                "name": message.author.name,
                "discriminator": message.author.discriminator,
                "avatar_url": str(message.author.avatar_url),
                "mod": not isinstance(message.channel, DMChannel),
            },
            "content": message.content,
            "type": type_,
            "attachments": [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "is_image": a.width is not None,
                    "size": a.size,
                    "url": a.url,
                }
                for a in message.attachments
            ],
        }

        return await self.logs.find_one_and_update(
            {"channel_id": channel_id}, {"$push": {"messages": data}}, return_document=True
        )

    async def post_log(self, channel_id: Union[int, str], data: dict) -> dict:
        return await self.logs.find_one_and_update(
            {"channel_id": str(channel_id)}, {"$set": data}, return_document=True
        )

    async def search_closed_by(self, user_id: Union[int, str]):
        return await self.logs.find(
            {"guild_id": str(self.bot.guild_id), "open": False, "closer.id": str(user_id)},
            {"messages": {"$slice": 5}},
        ).to_list(None)

    async def search_by_text(self, text: str, limit: Optional[int]):
        return await self.bot.db.logs.find(
            {
                "guild_id": str(self.bot.guild_id),
                "open": False,
                "$text": {"$search": f'"{text}"'},
            },
            {"messages": {"$slice": 5}},
        ).to_list(limit)

    def get_plugin_partition(self, cog):
        cls_name = cog.__class__.__name__
        return self.db.plugins[cls_name]


class PluginDatabaseClient:
    def __init__(self, bot):
        self.bot = bot

    def get_partition(self, cog):
        cls_name = cog.__class__.__name__
        return self.bot.api.db.plugins[cls_name]
