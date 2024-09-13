import discord
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from mongomock import MongoClient
from discord.ext import commands
from EventHandlers.onboarding import handle_guild_join, handle_message

@pytest_asyncio.fixture
def mock_collection_fixture():
    client = MongoClient()
    db = client.db
    return db

@pytest_asyncio.fixture
def connect_to_mongo_and_get_collection_fixture(mock_collection_fixture):
    def mock_connect(connection_string, db_name, collection_name):
        return getattr(mock_collection_fixture, collection_name)
    return mock_connect

@pytest_asyncio.fixture
async def bot():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    return bot

@pytest.mark.asyncio
async def test_handle_guild_join(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    guild = AsyncMock()
    guild.owner.id = 123456789
    guild.text_channels = [AsyncMock()]

    guild.me = MagicMock()
    guild.me.guild_permissions = MagicMock()
    guild.me.guild_permissions.manage_webhooks = True

    permissions = MagicMock()
    permissions.manage_webhooks = True
    guild.text_channels[0].permissions_for = MagicMock(return_value=permissions)


    async def mock_create_webhook(*args, **kwargs):
        mock_webhook = AsyncMock()
        mock_webhook.url = "https://discord.com/api/webhooks/123/abc"
        return mock_webhook

    guild.text_channels[0].create_webhook = mock_create_webhook

    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.onboarding.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    guild_onboarded_status = {}
    guild_states = {}

    await handle_guild_join(guild, guild_onboarded_status, guild_states)

    user_record = mock_collection_fixture.companies.find_one({"owner_ids": 123456789})
    assert user_record is not None
    assert user_record["webhook_url"] == "https://discord.com/api/webhooks/123/abc"
    assert user_record["onboarded"] == False
    
@pytest.mark.asyncio
async def test_handle_message_business_name(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    message = AsyncMock()
    message.author = AsyncMock()
    message.author.bot = False
    message.guild.id = 123456789
    message.guild.owner.id = 987654321
    message.content = "My Business"

    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.onboarding.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    mock_collection_fixture.companies.insert_one({
        "owner_ids": [987654321],
        "guild_id": message.guild.id,
        "business_name": None,
        "onboarded": False
    })

    guild_states = {123456789: "waiting_for_business_name"}

    await handle_message(message, guild_states)

    user_record = mock_collection_fixture.companies.find_one({"owner_ids": 987654321})
    assert user_record["business_name"] == "my business"

    message.channel.send.assert_called_with("Please give me a link to your website my business:")

@pytest.mark.asyncio
async def test_handle_message_website_link(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    message = AsyncMock()
    message.author = AsyncMock()
    message.author.bot = False
    message.guild.id = 123456789
    message.guild.owner.id = 987654321
    message.content = "https://www.mybusiness.com"

    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.onboarding.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    mock_collection_fixture.companies.insert_one({
        "owner_ids": [987654321],
        "guild_id": message.guild.id,
        "business_name": "my business",
        "onboarded": False
    })

    guild_states = {123456789: "waiting_for_website"}

    with patch("Helpers.helperClasses.ConfirmPricing") as mock_confirm_pricing:
        mock_confirm_pricing.return_value = AsyncMock()
        await handle_message(message, guild_states)

    user_record = mock_collection_fixture.companies.find_one({"owner_ids": 987654321})
    assert user_record["website_link"] == "https://www.mybusiness.com"

    message.channel.send.assert_any_call("We are currently running in beta, we are using this as an opportunity to discuss pricing that is commensurate to the value generated and your use cases.")

@pytest.mark.asyncio
async def test_handle_message_invalid_website(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    message = AsyncMock()
    message.author = AsyncMock()
    message.author.bot = False
    message.guild.id = 123456789
    message.guild.owner.id = 987654321
    message.content = "not_a_valid_url"

    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.onboarding.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    mock_collection_fixture.companies.insert_one({
        "owner_ids": [987654321],
        "guild_id": message.guild.id,
        "business_name": "my business",
        "onboarded": False
    })

    guild_states = {123456789: "waiting_for_website"}

    await handle_message(message, guild_states)

    message.channel.send.assert_called_with("That doesn't appear to be a valid URL. Please enter a valid website URL (e.g., https://www.example.com):")

    user_record = mock_collection_fixture.companies.find_one({"owner_ids": 987654321})
    assert "website_link" not in user_record