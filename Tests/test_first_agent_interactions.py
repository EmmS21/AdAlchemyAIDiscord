import discord
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from mongomock import MongoClient
from discord.ext import commands
from EventHandlers.first_agent_interations import handle_business, handle_research_paths, handle_user_personas

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
    db.marketing_agent.insert_one({
        "business_name": "test business",
        "list_of_paths_taken": ["path1", "path2"],
        "user_personas": ["persona1", "persona2"],
        "business": {"info": "some business info"}
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
    
    # Define slash commands here (mocked versions)
    @bot.tree.command(name="business")
    async def business(interaction: discord.Interaction):
        await handle_business(interaction, bot.check_onboarded_status)

    @bot.tree.command(name="research_paths")
    async def research_paths(interaction: discord.Interaction):
        await handle_research_paths(interaction, bot.check_onboarded_status)

    @bot.tree.command(name="user_personas")
    async def user_personas(interaction: discord.Interaction):
        await handle_user_personas(interaction, bot.check_onboarded_status)

    return bot

# Test for /business command
@pytest.mark.asyncio
async def test_business_command(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    # Mock the Interaction
    interaction = AsyncMock()
    interaction.user.id = 123456789

    # Mock the MongoDB connection
    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.first_agent_interations.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    # Mock the check_onboarded_status function
    async def mock_check_onboarded_status(owner_id):
        return True

    bot.check_onboarded_status = mock_check_onboarded_status

    # Execute the command
    await bot.tree.get_command("business").callback(interaction)

    # Assert the response
    interaction.response.send_message.assert_called_once()
    args, kwargs = interaction.response.send_message.call_args
    assert "No business data found for: Test Business in the latest document" in args[0]

# Test for /research_paths command
@pytest.mark.asyncio
async def test_research_paths_command(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    # Mock the Interaction
    interaction = AsyncMock()
    interaction.user.id = 123456789

    # Mock the MongoDB connection
    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.first_agent_interations.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    # Mock the check_onboarded_status function
    async def mock_check_onboarded_status(owner_id):
        return True

    bot.check_onboarded_status = mock_check_onboarded_status

    # Execute the command
    await bot.tree.get_command("research_paths").callback(interaction)

    # Assert the response
    interaction.response.send_message.assert_called_once()
    args, kwargs = interaction.response.send_message.call_args
    assert 'embed' in kwargs
    assert 'view' in kwargs
    assert isinstance(kwargs['embed'], discord.Embed)
    assert isinstance(kwargs['view'], discord.ui.View)
    
# Test for /user_personas command
@pytest.mark.asyncio
async def test_user_personas_command(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    # Mock the Interaction
    interaction = AsyncMock()
    interaction.user.id = 123456789

    # Mock the MongoDB connection
    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.first_agent_interations.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    # Mock the check_onboarded_status function
    async def mock_check_onboarded_status(owner_id):
        return True

    bot.check_onboarded_status = mock_check_onboarded_status

    # Execute the command
    await bot.tree.get_command("user_personas").callback(interaction)

    # Assert the response
    interaction.response.send_message.assert_called_once()
    args, kwargs = interaction.response.send_message.call_args
    assert 'embed' in kwargs  
    assert 'view' in kwargs  
    assert isinstance(kwargs['embed'], discord.Embed)  
    assert isinstance(kwargs['view'], discord.ui.View)  
# Test when user is not onboarded
@pytest.mark.asyncio
async def test_command_not_onboarded(bot, mock_collection_fixture, connect_to_mongo_and_get_collection_fixture, monkeypatch):
    # Mock the Interaction
    interaction = AsyncMock()
    interaction.user.id = 987654321

    # Mock the MongoDB connection
    monkeypatch.setenv("CONNECTION_STRING", "mongodb://localhost:27017")
    monkeypatch.setattr("EventHandlers.first_agent_interations.connect_to_mongo_and_get_collection", connect_to_mongo_and_get_collection_fixture)

    # Override the mock_check_onboarded_status function
    async def mock_check_onboarded_status(owner_id):
        return False

    bot.check_onboarded_status = mock_check_onboarded_status

    # Execute the command
    await bot.tree.get_command("business").callback(interaction)

    # Assert the response
    interaction.response.send_message.assert_called_once()
    args, kwargs = interaction.response.send_message.call_args
    assert "You don't have access to this command yet" in args[0]