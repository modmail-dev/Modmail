import os
import logging
import secrets
from datetime import datetime
from json import JSONDecodeError
from typing import Union, Optional

from discord import Member, DMChannel, TextChannel, Message
from discord.ext import commands

from aiohttp import ClientResponseError, ClientResponse

from core.utils import info

logger = logging.getLogger("Modmail")

prefix = os.getenv("LOG_URL_PREFIX", "/logs")
if prefix == "NONE":
    prefix = ""


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
    headers : Dict[str, str]
        The HTTP headers that will be sent along with the requiest.
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = bot.session
        self.headers: dict = None

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
        async with self.session.request(
            method, url, headers=headers, json=payload
        ) as resp:
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
        valid_keys = self.bot.config.valid_keys.difference(
            self.bot.config.protected_keys
        )
        return {k: v for k, v in data.items() if k in valid_keys}


class GitHub(RequestClient):
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
    HEAD = REPO + "/git/refs/heads/master"
    MERGE_URL = BASE + "/repos/{username}/modmail/merges"
    FORK_URL = REPO + "/forks"
    STAR_URL = BASE + "/user/starred/kyb3r/modmail"

    def __init__(self, bot, access_token: str = "", username: str = "", **kwargs):
        super().__init__(bot)
        self.access_token = access_token
        self.username = username
        self.avatar_url: str = kwargs.pop("avatar_url", "")
        self.url: str = kwargs.pop("url", "")
        if self.access_token:
            self.headers = {"Authorization": "token " + str(access_token)}

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
            resp: dict = await self.request(self.HEAD)
            sha = resp["object"]["sha"]

        payload = {"base": "master", "head": sha, "commit_message": "Updating bot"}

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
        self = cls(bot, bot.config.get("github_access_token"))
        resp: dict = await self.request("https://api.github.com/user")
        self.username: str = resp["login"]
        self.avatar_url: str = resp["avatar_url"]
        self.url: str = resp["html_url"]
        logger.info(info(f"GitHub logged in to: {self.username}"))
        return self


class ApiClient(RequestClient):
    def __init__(self, bot):
        super().__init__(bot)
        if self.token:
            self.headers = {"Authorization": "Bearer " + self.token}

    @property
    def token(self) -> Optional[str]:
        return self.bot.config.get("github_access_token")

    @property
    def db(self):
        return self.bot.db

    @property
    def logs(self):
        return self.db.logs

    async def get_user_logs(self, user_id: Union[str, int]) -> list:
        query = {"recipient.id": str(user_id), "guild_id": str(self.bot.guild_id)}

        projection = {"messages": {"$slice": 5}}
        return await self.logs.find(query, projection).to_list(None)

    async def get_log(self, channel_id: Union[str, int]) -> dict:
        return await self.logs.find_one({"channel_id": str(channel_id)})

    async def get_log_link(self, channel_id: Union[str, int]) -> str:
        doc = await self.get_log(channel_id)
        return f"{self.bot.config.log_url.strip('/')}{prefix}/{doc['key']}"

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

        return f"{self.bot.config.log_url.strip('/')}{prefix}/{key}"

    async def get_config(self) -> dict:
        conf = await self.db.config.find_one({"bot_id": self.bot.user.id})
        if conf is None:
            await self.db.config.insert_one({"bot_id": self.bot.user.id})
            return {"bot_id": self.bot.user.id}
        return conf

    async def update_config(self, data: dict):
        valid_keys = self.bot.config.valid_keys.difference(
            self.bot.config.protected_keys
        )

        toset = {k: v for k, v in data.items() if k in valid_keys}
        unset = {k: 1 for k in valid_keys if k not in data}

        return await self.db.config.update_one(
            {"bot_id": self.bot.user.id}, {"$set": toset, "$unset": unset}
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

    async def get_user_info(self) -> dict:
        user = await GitHub.login(self.bot)
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
        return self.bot.db.plugins[cls_name]
