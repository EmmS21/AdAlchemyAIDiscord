import discord
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from mongomock import MongoClient
from discord.ext import commands
from EventHandlers.ad_interactions import handle_keywords, handle_adtext, handle_upload_credentials, handle_create_ad
import json

# Fixture for the mock MongoDB collection
@pytest_asyncio.fixture
def mock_collection_fixture():
    client = MongoClient()
    db = client.db
    db.companies.insert_one({
        "owner_ids": [123456789],
        "business_name": "Test Business",
        "website_link": "https://www.testbusiness.com",
        "onboarded": True
    })
    db.judge_data.insert_one({
        "business_name": "test business",
        "selected_keywords": ["keyword1", "keyword2"],
        "keywords": ["keyword3", "keyword4"],
        "ad_variations": ["ad1", "ad2"],
        "finalized_ad_text": ["final_ad1"],
        "last_update": "2023-01-01T00:00:00Z"
    })
    db.credentials.insert_one({
        "business_name": "test business",
        "credentials": {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "refresh_token": "test_refresh_token",
            "developer_token": "test_developer_token",
            "customer_id": "test_customer_id"
        }
    })
    return db

# Mock function to return the shared mock_collection
@pytest_asyncio.fixture
def connect_to_mongo_and_get_collection_fixture(mock_collection_fixture):
    def mock_connect(connection_string, db_name, collection_name):
        return getattr(mock_collection_fixture, collection_name)
    return mock_connect

# Fixture for the Discord bot
@pytest_asyncio.fixture
async def bot():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    return bot

# Test for /keywords command
@pytest.mark.asyncio
async def test_keywords_command(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    # Mock the Interaction
    interaction = AsyncMock()
    interaction.user.id = 123456789

    # Mock the MongoDB connection
    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.ad_interactions.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    # Mock the check_onboarded_status function
    async def mock_check_onboarded_status(owner_id):
        return True

    # Execute the command
    await handle_keywords(interaction, mock_check_onboarded_status)

    # Assert the response
    interaction.followup.send.assert_called_once()
    args, kwargs = interaction.followup.send.call_args
    assert 'ephemeral' in kwargs

# Test for /adtext command
@pytest.mark.asyncio
async def test_adtext_command(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    # Mock the Interaction
    interaction = AsyncMock()
    interaction.user.id = 123456789

    # Mock the MongoDB connection
    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.ad_interactions.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    # Mock the check_onboarded_status function
    async def mock_check_onboarded_status(owner_id):
        return True

    # Execute the command
    await handle_adtext(interaction, mock_check_onboarded_status)

    # Assert the response
    interaction.response.send_message.assert_called_once()
    args, kwargs = interaction.response.send_message.call_args
    assert 'ephemeral' in kwargs

# Test for /uploadcredentials command
@pytest.mark.asyncio
async def test_upload_credentials_command(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    # Mock the Interaction
    interaction = AsyncMock()
    interaction.user.id = 123456789
    interaction.data = {
        "options": [
            {"name": "credentials_file", "value": "test_credentials.json"},
            {"name": "customer_id", "value": "test_customer_id"}
        ]
    }
    interaction.guild.id = 987654321

    # Mock the MongoDB connection
    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.ad_interactions.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    # Mock the check_onboarded_status function
    async def mock_check_onboarded_status(owner_id):
        return True

    # Mock the credentials file
    credentials_file = MagicMock()
    credentials_file.read = AsyncMock(return_value=json.dumps({
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "refresh_token": "test_refresh_token",
        "developer_token": "test_developer_token",
        "customer_id": "test_customer_id",
        "project_id": "test_project_id",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "use_proto_plus": True
    }).encode('utf-8'))

    # Execute the command
    await handle_upload_credentials(interaction, credentials_file, "test_customer_id", mock_check_onboarded_status)

    # Assert the response
    interaction.followup.send.assert_called_once()
    args, kwargs = interaction.followup.send.call_args
    assert "Credentials uploaded and saved successfully." in args[0]

# Test for /createad command
@pytest.mark.asyncio
async def test_create_ad_command(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    # Mock the Interaction
    interaction = AsyncMock()
    interaction.user.id = 123456789

    # Mock the MongoDB connection
    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.ad_interactions.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    # Mock the check_onboarded_status function
    async def mock_check_onboarded_status(owner_id):
        return True

    # Execute the command
    await handle_create_ad(interaction, mock_check_onboarded_status)

    # Assert the response
    interaction.followup.send.assert_called_once()
    args, kwargs = interaction.followup.send.call_args
    assert "Please use /uploadcredentials to upload your Google Ads credentials." in args[0]
