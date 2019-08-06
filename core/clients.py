import logging
import secrets
from datetime import datetime
from json import JSONDecodeError
from typing import Union

from discord import Member, DMChannel, TextChannel, Message

from aiohttp import ClientResponseError, ClientResponse

logger = logging.getLogger("Modmail")


class RequestClient:
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

    def __init__(self, bot):
        self.bot = bot
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
        async with self.session.request(
            method, url, headers=headers, json=payload
        ) as resp:
            if return_response:
                return resp
            try:
                return await resp.json()
            except (JSONDecodeError, ClientResponseError):
                return await resp.text()


class ApiClient(RequestClient):
    @property
    def db(self):
        return self.bot.db

    @property
    def logs(self):
        return self.db.logs

    async def get_user_logs(self, user_id: Union[str, int]) -> list:
        query = {"recipient.id": str(user_id), "guild_id": str(self.bot.guild_id)}
        projection = {"messages": {"$slice": 5}}
        logger.debug("Retrieving user %s logs.", user_id)

        return await self.logs.find(query, projection).to_list(None)

    async def get_log(self, channel_id: Union[str, int]) -> dict:
        logger.debug("Retrieving channel %s logs.", channel_id)
        return await self.logs.find_one({"channel_id": str(channel_id)})

    async def get_log_link(self, channel_id: Union[str, int]) -> str:
        doc = await self.get_log(channel_id)
        logger.debug("Retrieving log link for channel %s.", channel_id)
        prefix = self.bot.config["log_url_prefix"].strip("/")
        if prefix == "NONE":
            prefix = ""
        return f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{doc['key']}"

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
            return await self.db.config.update_one(
                {"bot_id": self.bot.user.id}, {"$set": toset}
            )
        if unset:
            return await self.db.config.update_one(
                {"bot_id": self.bot.user.id}, {"$unset": unset}
            )

    async def edit_message(self, message_id: Union[int, str], new_content: str) -> None:
        await self.logs.update_one(
            {"messages.message_id": str(message_id)},
            {"$set": {"messages.$.content": new_content, "messages.$.edited": True}},
        )

    async def append_log(
        self,
        message: Message,
        channel_id: Union[str, int] = "",
        type_: str = "thread_message",
    ) -> dict:
        channel_id = str(channel_id) or str(message.channel.id)
        data = {
            "timestamp": str(message.created_at),
            "message_id": str(message.id),
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
            {"channel_id": channel_id},
            {"$push": {f"messages": data}},
            return_document=True,
        )

    async def post_log(self, channel_id: Union[int, str], data: dict) -> dict:
        return await self.logs.find_one_and_update(
            {"channel_id": str(channel_id)},
            {"$set": {k: v for k, v in data.items()}},
            return_document=True,
        )


class PluginDatabaseClient:
    def __init__(self, bot):
        self.bot = bot

    def get_partition(self, cog):
        cls_name = cog.__class__.__name__
        return self.bot.db.plugins[cls_name]
