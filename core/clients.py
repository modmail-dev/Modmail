import secrets
import sys
from datetime import datetime
from json import JSONDecodeError
from typing import Union, Optional

from discord import Member, DMChannel, TextChannel, Message
from discord.ext import commands

from aiohttp import ClientResponseError, ClientResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConfigurationError

from core.models import InvalidConfigError, getLogger

logger = getLogger(__name__)


class GitHub:
    """
    The client for interacting with GitHub API.
    Parameters
    ----------
    bot : Bot
        The Modmail bot.
    access_token : str, optional
        GitHub's access token.
    username : str, optional
        GitHub username.
    avatar_url : str, optional
        URL to the avatar in GitHub.
    url : str, optional
        URL to the GitHub profile.
    Attributes
    ----------
    bot : Bot
        The Modmail bot.
    access_token : str
        GitHub's access token.
    username : str
        GitHub username.
    avatar_url : str
        URL to the avatar in GitHub.
    url : str
        URL to the GitHub profile.
    Class Attributes
    ----------------
    BASE : str
        GitHub API base URL.
    REPO : str
        Modmail repo URL for GitHub API.
    HEAD : str
        Modmail HEAD URL for GitHub API.
    MERGE_URL : str
        URL for merging upstream to master.
    FORK_URL : str
        URL to fork Modmail.
    STAR_URL : str
        URL to star Modmail.
    """

    BASE = "https://api.github.com"
    REPO = BASE + "/repos/kyb3r/modmail"
    MERGE_URL = BASE + "/repos/{username}/modmail/merges"
    FORK_URL = REPO + "/forks"
    STAR_URL = BASE + "/user/starred/kyb3r/modmail"

    def __init__(self, bot, access_token: str = "", username: str = "", **kwargs):
        self.bot = bot
        self.session = bot.session
        self.headers: Optional[dict] = None
        self.access_token = access_token
        self.username = username
        self.avatar_url: str = kwargs.pop("avatar_url", "")
        self.url: str = kwargs.pop("url", "")
        if self.access_token:
            self.headers = {"Authorization": "token " + str(access_token)}

    @property
    def BRANCH(self):
        return "master" if not self.bot.version.is_prerelease else "development"

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
        if headers is not None:
            headers.update(self.headers)
        else:
            headers = self.headers
        async with self.session.request(method, url, headers=headers, json=payload) as resp:
            if return_response:
                return resp
            try:
                return await resp.json()
            except (JSONDecodeError, ClientResponseError):
                return await resp.text()

    def filter_valid(self, data):
        """
        Filters configuration keys that are accepted.
        Parameters
        ----------
        data : Dict[str, Any]
            The data that needs to be cleaned.
        Returns
        -------
        Dict[str, Any]
            Filtered `data` to keep only the accepted pairs.
        """
        valid_keys = self.bot.config.valid_keys.difference(self.bot.config.protected_keys)
        return {k: v for k, v in data.items() if k in valid_keys}

    async def update_repository(self, sha: str = None) -> Optional[dict]:
        """
        Update the repository from Modmail main repo.
        Parameters
        ----------
        sha : Optional[str], optional
            The commit SHA to update the repository.
        Returns
        -------
        Optional[dict]
            If the response is a dict.
        """
        if not self.username:
            raise commands.CommandInvokeError("Username not found.")

        if sha is None:
            resp: dict = await self.request(self.REPO + "/git/refs/heads/" + self.BRANCH)
            sha = resp["object"]["sha"]

        payload = {"base": self.BRANCH, "head": sha, "commit_message": "Updating bot"}

        merge_url = self.MERGE_URL.format(username=self.username)

        resp = await self.request(merge_url, method="POST", payload=payload)
        if isinstance(resp, dict):
            return resp

    async def fork_repository(self) -> None:
        """
        Forks Modmail's repository.
        """
        await self.request(self.FORK_URL, method="POST")

    async def has_starred(self) -> bool:
        """
        Checks if shared Modmail.
        Returns
        -------
        bool
            `True`, if Modmail was starred.
            Otherwise `False`.
        """
        resp = await self.request(self.STAR_URL, return_response=True)
        return resp.status == 204

    async def star_repository(self) -> None:
        """
        Stars Modmail's repository.
        """
        await self.request(self.STAR_URL, method="PUT", headers={"Content-Length": "0"})

    @classmethod
    async def login(cls, bot) -> "GitHub":
        """
        Logs in to GitHub with configuration variable information.
        Parameters
        ----------
        bot : Bot
            The Modmail bot.
        Returns
        -------
        GitHub
            The newly created `GitHub` object.
        """
        self = cls(bot, bot.config.get("github_token"))
        resp: dict = await self.request("https://api.github.com/user")
        if resp.get("login"):
            self.username = resp["login"]
            self.avatar_url = resp["avatar_url"]
            self.url = resp["html_url"]
            logger.info(f"GitHub logged in to: {self.username}")
            return self
        else:
            raise InvalidConfigError("Invalid github token")


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

    async def create_log_entry(self, recipient: Member, channel: TextChannel, creator: Member) -> str:
        return NotImplemented

    async def delete_log_entry(self, key: str) -> bool:
        return NotImplemented

    async def get_config(self) -> dict:
        return NotImplemented

    async def update_config(self, data: dict):
        return NotImplemented

    async def edit_message(self, message_id: Union[int, str], new_content: str):
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

    async def create_note(self, recipient: Member, message: Message, message_id: Union[int, str]):
        return NotImplemented

    async def find_notes(self, recipient: Member):
        return NotImplemented

    async def update_note_ids(self, ids: dict):
        return NotImplemented

    async def delete_note(self, message_id: Union[int, str]):
        return NotImplemented

    async def edit_note(self, message_id: Union[int, str], message: str):
        return NotImplemented

    def get_plugin_partition(self, cog):
        return NotImplemented

    async def update_repository(self) -> dict:
        return NotImplemented

    async def get_user_info(self) -> Optional[dict]:
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
                "Your MongoDB CONNECTION_URI might be copied wrong, try re-copying from the source again. "
                "Otherwise noted in the following message:\n%s",
                e,
            )
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

    async def validate_database_connection(self, *, ssl_retry=True):
        try:
            await self.db.command("buildinfo")
        except Exception as exc:
            logger.critical("Something went wrong while connecting to the database.")
            message = f"{type(exc).__name__}: {str(exc)}"
            logger.critical(message)
            if "CERTIFICATE_VERIFY_FAILED" in message and ssl_retry:
                mongo_uri = self.bot.config["connection_uri"]
                if mongo_uri is None:
                    mongo_uri = self.bot.config["mongo_uri"]
                for _ in range(3):
                    logger.warning(
                        "FAILED TO VERIFY SSL CERTIFICATE, ATTEMPTING TO START WITHOUT SSL (UNSAFE)."
                    )
                logger.warning(
                    "To fix this warning, check there's no proxies blocking SSL cert verification, "
                    'run "Certificate.command" on MacOS, '
                    'and check certifi is up to date "pip3 install --upgrade certifi".'
                )
                self.db = AsyncIOMotorClient(mongo_uri, tlsAllowInvalidCertificates=True).modmail_bot
                return await self.validate_database_connection(ssl_retry=False)
            if "ServerSelectionTimeoutError" in message:
                logger.critical(
                    "This may have been caused by not whitelisting "
                    "IPs correctly. Make sure to whitelist all "
                    "IPs (0.0.0.0/0) https://i.imgur.com/mILuQ5U.png"
                )

            if "OperationFailure" in message:
                logger.critical(
                    "This is due to having invalid credentials in your MongoDB CONNECTION_URI. "
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
        return f"{self.bot.config['log_url'].strip('/')}{'/' + prefix if prefix else ''}/{doc['key']}"

    async def create_log_entry(self, recipient: Member, channel: TextChannel, creator: Member) -> str:
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
        unset = self.bot.config.filter_valid({k: 1 for k in self.bot.config.all_keys if k not in data})

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

    async def create_note(self, recipient: Member, message: Message, message_id: Union[int, str]):
        await self.db.notes.insert_one(
            {
                "recipient": str(recipient.id),
                "author": {
                    "id": str(message.author.id),
                    "name": message.author.name,
                    "discriminator": message.author.discriminator,
                    "avatar_url": str(message.author.avatar_url),
                },
                "message": message.content,
                "message_id": str(message_id),
            }
        )

    async def find_notes(self, recipient: Member):
        return await self.db.notes.find({"recipient": str(recipient.id)}).to_list(None)

    async def update_note_ids(self, ids: dict):
        for object_id, message_id in ids.items():
            await self.db.notes.update_one({"_id": object_id}, {"$set": {"message_id": message_id}})

    async def delete_note(self, message_id: Union[int, str]):
        await self.db.notes.delete_one({"message_id": str(message_id)})

    async def edit_note(self, message_id: Union[int, str], message: str):
        await self.db.notes.update_one({"message_id": str(message_id)}, {"$set": {"message": message}})

    def get_plugin_partition(self, cog):
        cls_name = cog.__class__.__name__
        return self.db.plugins[cls_name]

    async def update_repository(self) -> dict:
        user = await GitHub.login(self.bot)
        data = await user.update_repository()
        return {
            "data": data,
            "user": {
                "username": user.username,
                "avatar_url": user.avatar_url,
                "url": user.url,
            },
        }

    async def get_user_info(self) -> Optional[dict]:
        try:
            user = await GitHub.login(self.bot)
        except InvalidConfigError:
            return None
        else:
            return {
                "user": {
                    "username": user.username,
                    "avatar_url": user.avatar_url,
                    "url": user.url,
                }
            }


class PluginDatabaseClient:
    def __init__(self, bot):
        self.bot = bot

    def get_partition(self, cog):
        cls_name = cog.__class__.__name__
        return self.bot.api.db.plugins[cls_name]
