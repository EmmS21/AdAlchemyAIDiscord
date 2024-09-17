import aiohttp
import discord
import os
import dotenv
import logging
import json
from pathlib import Path
from collections import defaultdict
from discord import app_commands, Embed
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
import EventHandlers.onboarding as onboarding
import Helpers.helperfuncs as helperfuncs
import Helpers.helperClasses as helperClasses
import EventHandlers.first_agent_interations as first_agent
import EventHandlers.ad_interactions as ad_interactions

dotenv.load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
guild_business_data = defaultdict(dict)
guild_onboarded_status = {}
user_data = {}

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
intents.members = True 

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

user_states = {}
guild_states = {}
setup_user_id = None

async def sync_commands():
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

async def check_onboarded_status(owner_id):
    CONNECTION_STRING = os.getenv("CONNECTION_STRING")
    mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
    
    owner_record = mappings_collection.find_one({"owner_ids": owner_id})
    if owner_record and owner_record.get("onboarded") == True:
        return True
    return False

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    await sync_commands()

@client.event
async def on_guild_join(guild):
    await onboarding.handle_guild_join(guild, guild_onboarded_status,guild_states)

@client.event
async def on_message(message):
    print(f"Handling message with ID: {message.id}, content: {message.content}, author: {message.author}, webhook_id: {message.webhook_id}")

    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    CONNECTION_STRING = os.getenv("CONNECTION_STRING")
    mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")

    if message.webhook_id:
        webhook = await client.fetch_webhook(message.webhook_id)
        if webhook.name == "onboarding":
            await onboarding.handle_message(message, mappings_collection, guild_states, is_webhook=True)
    else:
        await onboarding.handle_message(message, mappings_collection, guild_states, is_webhook=False)

class HelpView(discord.ui.View):
    def __init__(self, pages):
        super().__init__(timeout=300) 
        self.pages = pages
        self.current_page = 0
        self.update_button_states()

    def update_button_states(self):
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.pages) - 1)


    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_button_states()
            await interaction.response.edit_message(content=self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_button_states()
            await interaction.response.edit_message(content=self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()


@tree.command(name="website", description="Get the AdAlchemy AI website link")
async def website(interaction: discord.Interaction):
    website_url = "https://www.adalchemyai.com/"
    await interaction.response.send_message(f"Here's the AdAlchemy AI website: {website_url}", ephemeral=True)

@tree.command(name="help", description="Get help on how to use AdAlchemyAI")
async def help_command(interaction: discord.Interaction):
    help_file_path = Path("Responses/help.md")
    if help_file_path.exists():
        with open(help_file_path, "r") as help_file:
            help_content = help_file.read()
        pages = [help_content[i:i+2000] for i in range(0, len(help_content), 2000)]
        view = HelpView(pages)
        await interaction.response.send_message(pages[0], view=view, ephemeral=True)
    else:
        await interaction.response.send_message("Sorry, the help file couldn't be found.", ephemeral=True)

@tree.command(name="business", description="View and edit business information")
async def business(interaction: discord.Interaction):
    first_agent.handle_business(interaction, check_onboarded_status)

@tree.command(name="research_paths", description="View and add research paths for your business")
async def research_paths(interaction: discord.Interaction):
    first_agent.handle_research_paths(interaction, check_onboarded_status)

@tree.command(name="user_personas", description="View and manage user personas for your business")
async def user_personas(interaction: discord.Interaction):
    first_agent.handle_user_personas(interaction, check_onboarded_status)

@tree.command(name="keywords", description="View and select keywords for your business")
async def keywords(interaction: discord.Interaction):
    ad_interactions.handle_keywords(interaction, check_onboarded_status)

@tree.command(name="adtext", description="View and edit ad variations for your business")
async def adtext(interaction: discord.Interaction):
    ad_interactions.handle_adtext(interaction, check_onboarded_status)

@tree.command(name="uploadcredentials", description="Upload your Google Ads API credentials")
async def upload_credentials(interaction: discord.Interaction, credentials_file: discord.Attachment, customer_id: str):
    await ad_interactions.handle_upload_credentials(interaction, credentials_file, customer_id)

@tree.command(name="createad", description="Create a new ad or add to an existing campaign")
async def create_ad(interaction: discord.Interaction):
    ad_interactions.handle_create_ad(interaction, check_onboarded_status)

client.run(os.getenv('DISCORD_TOKEN'))
