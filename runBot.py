from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
from Helpers.helperfuncs import website_exists_in_db
from Helpers.helperClasses import ConfirmPricing
from Helpers.pagination import create_paginated_embed, PaginationView
import discord
from discord import app_commands
import os
import dotenv
from collections import defaultdict
import re
from pathlib import Path

dotenv.load_dotenv()
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
    print('owner_id', owner_id)
    CONNECTION_STRING = os.getenv("CONNECTION_STRING")
    mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
    
    owner_record = mappings_collection.find_one({"owner_ids": owner_id})
    print('guild', owner_record)
    if owner_record and owner_record.get("onboarded") == True:
        return True
    return False

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    await sync_commands()

@client.event
async def on_guild_join(guild):
    CONNECTION_STRING = os.getenv("CONNECTION_STRING")
    mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")

    owner_id = guild.owner.id

    # Create webhook
    webhook_url = None
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).manage_webhooks:
            try:
                webhook = await channel.create_webhook(name="AdAlchemyAI Notifications")
                webhook_url = webhook.url
                break
            except Exception as e:
                print(f"Failed to create webhook in channel {channel.id}: {str(e)}")

    # Check if the owner already has a record
    user_record = mappings_collection.find_one({"owner_ids": owner_id})

    if user_record:
        # Update existing user
        update_data = {
            "$addToSet": {"owner_ids": owner_id},
            "$set": {"webhook_url": webhook_url}
        }
        mappings_collection.update_one({"_id": user_record["_id"]}, update_data)

        business_name = user_record.get("business_name", "valued business")
        welcome_back_message = f"Welcome back {business_name}!"
        
        if user_record.get("onboarded") == True:
            calendly_message = "You have full access to all commands. Type / to see available commands."
            guild_onboarded_status[guild.id] = True
        else:
            calendly_message = "Please schedule a date to complete your onboarding and discuss your business needs: [Calendly Link](https://calendly.com/emmanuel-emmanuelsibanda/30min)"
            guild_onboarded_status[guild.id] = False

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(welcome_back_message)
                await channel.send(calendly_message)
                break
    else:
        # New user
        new_user_data = {
            "owner_ids": [owner_id],
            "webhook_url": webhook_url,
            "business_name": None,
            "website_link": None,
            "onboarded": False
        }
        mappings_collection.insert_one(new_user_data)

        welcome_message = """
        Hello! I am AdAlchemyAI, a bot to help you get good leads for a cost-effective price for your business by automating the process of setting up, running, and optimizing your Google Ads. I only run ads after you manually approve the keywords I researched, the ad text ideas I generate, and the information I use to carry out my research.

        But for now, I would like to learn more about you and your business.
        """
        first_question = "What is the name of your business?"
        guild_onboarded_status[guild.id] = False

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(welcome_message)
                await channel.send(first_question)
                break

        guild_states[guild.id] = "waiting_for_business_name"

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    guild_id = message.guild.id
    current_state = guild_states.get(guild_id)

    CONNECTION_STRING = os.getenv("CONNECTION_STRING")
    mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
    
    # Use owner_ids to find the user record
    user_record = mappings_collection.find_one({"owner_ids": message.guild.owner.id})
    
    if not user_record:
        print(f"No document found for owner_id: {message.guild.owner.id}. Skipping update.")
        return

    if current_state == "waiting_for_business_name":
        business_name = message.content.lower()
        mappings_collection.update_one(
            {"_id": user_record["_id"]},
            {"$set": {"business_name": business_name}}
        )
        await message.channel.send(f"Please give me a link to your website {business_name}:")
        guild_states[guild_id] = "waiting_for_website"

    elif current_state == "waiting_for_website":
        url_pattern = re.compile(
            r'^(?:http|ftp)s?://'  
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' 
            r'localhost|' 
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?' 
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        if re.match(url_pattern, message.content):
            website_link = message.content
            mappings_collection.update_one(
                {"_id": user_record["_id"]},
                {"$set": {"website_link": website_link}}
            )
            await message.channel.send("We are currently running in beta, we are using this as an opportunity to discuss pricing that is commensurate to the value generated and your use cases.")
                       
            user_record = mappings_collection.find_one({"_id": user_record["_id"]})
            business_name = user_record.get("business_name", "your business")
            view = ConfirmPricing(guild_id, business_name, website_link)
            await message.channel.send("Please confirm your interest in joining the AdAlchemyAI waiting list", view=view)
            guild_states[guild_id] = "waiting_for_consent"
        else:
            await message.channel.send("That doesn't appear to be a valid URL. Please enter a valid website URL (e.g., https://www.example.com):")

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

@tree.command(name="business", description="Access business information")
async def business(interaction: discord.Interaction):
    user_id = interaction.user.id
    is_onboarded = await check_onboarded_status(user_id)
    
    if is_onboarded:
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
        user_record = mappings_collection.find_one({"owner_ids": user_id})
        
        if user_record and "business_name" in user_record:
            business_name = user_record["business_name"]
            business_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "marketing_agent", business_name.lower())
            
            if business_collection is not None:
                latest_document = business_collection.find_one(sort=[("_id", -1)])
                
                if latest_document and 'business' in latest_document:
                    business_data = latest_document['business']
                    pages = create_paginated_embed({business_data})
                    
                    if len(pages) > 1:
                        view = PaginationView(pages)
                        await interaction.response.send_message(pages[0], view=view, ephemeral=True)
                    else:
                        await interaction.response.send_message(pages[0], ephemeral=True)
                else:
                    await interaction.response.send_message(f"No data found in the collection for the business: {business_name}", ephemeral=True)
            else:
                await interaction.response.send_message(f"No collection found for the business: {business_name}", ephemeral=True)
        else:
            await interaction.response.send_message("Unable to find your business name. Please make sure you've completed the initial setup.", ephemeral=True)
    else:
        calendly_link = "https://calendly.com/emmanuel-emmanuelsibanda/30min"
        await interaction.response.send_message(
            f"You don't have access to this command yet. Please complete the onboarding process by scheduling a call: {calendly_link}",
            ephemeral=True
        )

client.run(os.getenv('DISCORD_TOKEN'))
