import aiohttp
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
from Helpers.helperfuncs import create_campaign_flow, get_campaigns, website_exists_in_db, get_latest_document
from Helpers.helperClasses import ConfirmPricing, BusinessView, ResearchPathsView, UserPersonaView, KeywordPaginationView, AdTextView, AuthCompletedView
import discord
from discord import app_commands, Embed
import os
import dotenv
from collections import defaultdict
import re
from pathlib import Path
import logging
from datetime import datetime, timezone
import json

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
            "onboarded": False,
            "created_at": datetime.now(timezone.utc)
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

@tree.command(name="business", description="View and edit business information")
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
                latest_document = get_latest_document(business_collection)
                
                if latest_document and 'business' in latest_document:
                    business_data = latest_document['business']
                    
                    if not business_data:
                        await interaction.response.send_message("No business information found in the latest document.")
                        return
                    
                    view = BusinessView(business_data)
                    embed = view.get_embed()
                    await interaction.response.send_message(embed=embed, view=view)
                else:
                    await interaction.response.send_message(f"No business data found for: {business_name} in the latest document", ephemeral=True)
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

@tree.command(name="research_paths", description="View and add research paths for your business")
async def research_paths(interaction: discord.Interaction):
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
                latest_document = get_latest_document(business_collection)
                
                if latest_document and 'list_of_paths_taken' in latest_document:
                    paths = latest_document['list_of_paths_taken']
                    
                    if not paths:
                        await interaction.response.send_message("No research paths found for your business in the latest document. Use the 'Add Path' button to add one.")
                        return
                    
                    view = ResearchPathsView(paths, business_name)
                    embed = view.get_embed()
                    await interaction.response.send_message(embed=embed, view=view)
                else:
                    view = ResearchPathsView([], business_name)
                    embed = Embed(title="Research Paths", description="No research paths found in the latest document. Use the 'Add Path' button to add one.", color=discord.Color.blue())
                    await interaction.response.send_message(embed=embed, view=view)
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

@tree.command(name="user_personas", description="View and manage user personas for your business")
async def user_personas(interaction: discord.Interaction):
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
                latest_document = get_latest_document(business_collection)
                
                if latest_document and 'user_personas' in latest_document:
                    personas = latest_document['user_personas']
                    if isinstance(personas, str):
                        personas = [personas] 
                    
                    view = UserPersonaView(personas, business_name)
                    embed = view.get_embed()
                    await interaction.response.send_message(embed=embed, view=view)
                else:
                    view = UserPersonaView([], business_name)
                    embed = discord.Embed(title="User Personas", description="No user personas found in the latest document. Add a new one!", color=discord.Color.blue())
                    await interaction.response.send_message(embed=embed, view=view)
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

@tree.command(name="keywords", description="View and select keywords for your business")
async def keywords(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        user_id = interaction.user.id
        logger.info(f"Keywords command initiated by user {user_id}")
        
        is_onboarded = await check_onboarded_status(user_id)
        logger.info(f"User onboarded status: {is_onboarded}")
        
        if not is_onboarded:
            calendly_link = "https://calendly.com/emmanuel-emmanuelsibanda/30min"
            await interaction.followup.send(
                f"You don't have access to this command yet. Please complete the onboarding process by scheduling a call: {calendly_link}",
                ephemeral=True
            )
            return

        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
        user_record = mappings_collection.find_one({"owner_ids": user_id})
        
        if not user_record or "business_name" not in user_record:
            await interaction.followup.send("Unable to find your business name. Please make sure you've completed the initial setup.", ephemeral=True)
            return

        business_name = user_record["business_name"]
        logger.info(f"Business name: {business_name}")
        
        business_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "judge_data", business_name)
        if business_collection is None:
            await interaction.followup.send(f"No collection found for the business: {business_name}", ephemeral=True)
            return

        latest_document = get_latest_document(business_collection)
        logger.info(f"Latest document retrieved: {latest_document is not None}")
        
        if not latest_document:
            await interaction.followup.send(f"No document found for business: {business_name}", ephemeral=True)
            return

        selected_keywords = []
        new_keywords = []
        title = ""
        last_update = latest_document.get('last_update', 'N/A') 

        
        if 'selected_keywords' in latest_document and latest_document['selected_keywords']:
            selected_keywords = latest_document['selected_keywords']
            title = "Previously Selected Keywords"
        if 'keywords' in latest_document:
            new_keywords = latest_document['keywords']
            if not title:
                title = "Available Keywords"
        
        logger.info(f"Selected keywords: {len(selected_keywords)}")
        logger.info(f"New keywords: {len(new_keywords)}")
        logger.info(f"Last update: {last_update}")

        if not selected_keywords and not new_keywords:
            await interaction.followup.send("No keywords found for your business.", ephemeral=True)
            return

        view = KeywordPaginationView(selected_keywords, new_keywords, business_collection, title, last_update)
        embed = view.get_embed()
        await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        logger.error(f"Error in keywords command: {str(e)}", exc_info=True)
        await interaction.followup.send("An error occurred while processing your request. Please try again later or contact support if the issue persists.", ephemeral=True)


@tree.command(name="adtext", description="View and edit ad variations for your business")
async def adtext(interaction: discord.Interaction):
    user_id = interaction.user.id
    is_onboarded = await check_onboarded_status(user_id)
    
    if is_onboarded:
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
        user_record = mappings_collection.find_one({"owner_ids": user_id})
        
        if user_record and "business_name" in user_record:
            business_name = user_record["business_name"]
            business_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "judge_data", business_name.lower())
            
            if business_collection is not None:
                latest_document = get_latest_document(business_collection)
                
                if latest_document and 'ad_variations' in latest_document:
                    ad_variations = latest_document['ad_variations']
                    finalized_ad_texts = latest_document.get('finalized_ad_text', [])
                    last_update = latest_document.get('last_update', 'N/A')
                    
                    view = AdTextView(ad_variations, finalized_ad_texts, business_collection, last_update)
                    embed = view.get_embed()
                    await interaction.response.send_message(embed=embed, view=view)
                else:
                    await interaction.response.send_message("No ad variations found for your business in the latest document.", ephemeral=True)
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

@tree.command(name="uploadcredentials", description="Upload your Google Ads API credentials")
async def upload_credentials(interaction: discord.Interaction, credentials_file: discord.Attachment, customer_id: str):
    user_id = interaction.user.id
    is_onboarded = await check_onboarded_status(user_id)
    
    if is_onboarded:
        await interaction.response.defer(thinking=True)
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
        user_record = mappings_collection.find_one({"owner_ids": user_id})
        
        if user_record and "business_name" in user_record:
            business_name = user_record["business_name"]
            
            if not credentials_file.filename.endswith('.json'):
                await interaction.followup.send("Error: Please upload a JSON file.")
                return
            
            try:
                credentials_content = await credentials_file.read()
                credentials_json = json.loads(credentials_content.decode('utf-8'))
                required_fields = ['client_id', 'project_id', 'auth_uri', 'auth_provider_x509_cert_url', 'client_secret', 'use_proto_plus']
                for field in required_fields:
                    if field not in credentials_json:
                        await interaction.followup.send(f"Error: Missing required field '{field}' in credentials file.")
                        return

                if not isinstance(credentials_json['use_proto_plus'], bool):
                    await interaction.followup.send("Error: 'use_proto_plus' must be a boolean value.")
                    return
                
                credentials_json['developer_token'] = os.getenv('DEVELOPER_TOKEN')
                credentials_json['customer_id'] = customer_id
                credentials_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "credentials", business_name)
                credentials_collection.update_one({}, {"$set": {"credentials": credentials_json}}, upsert=True)
                await interaction.followup.send("Credentials uploaded and saved successfully.")
            except json.JSONDecodeError:
                await interaction.followup.send("Error: Uploaded file does not contain valid JSON.")
            except Exception as e:
                await interaction.followup.send(f"An unexpected error occurred: {str(e)}")
            
        else:
            await interaction.followup.send("Unable to find your business name. Please make sure you've completed the initial setup.", ephemeral=True)
            return     
    else:
        calendly_link = "https://calendly.com/emmanuel-emmanuelsibanda/30min"
        await interaction.response.send_message(
            f"You don't have access to this command yet. Please complete the onboarding process by scheduling a call: {calendly_link}",
            ephemeral=True
        )

@tree.command(name="createad", description="Create a new ad or add to an existing campaign")
async def create_ad(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    user_id = interaction.user.id
    is_onboarded = await check_onboarded_status(user_id)
    
    if is_onboarded:
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
        user_record = mappings_collection.find_one({"owner_ids": user_id})
        
        if user_record and "business_name" in user_record:
            business_name = user_record["business_name"]
            business_website = user_record["website_link"]
            credentials_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "credentials", business_name)
            credentials_document = credentials_collection.find_one()
            if not credentials_document or 'credentials' not in credentials_document:
                await interaction.followup.send("Please use /uploadcredentials to upload your Google Ads credentials.")
                return
            credentials = credentials_document['credentials']
            customer_id = credentials.pop('customer_id', None)

            if not customer_id:
                await interaction.followup.send("Error: Customer ID not found in credentials.", ephemeral=True)
                return
            
            if 'web' not in credentials:
                web_credentials = {
                    "web": {
                        key: value for key, value in credentials.items() 
                        if key not in ['developer_token', 'use_proto_plus', 'customer_id']
                    }
                }
                web_credentials['developer_token'] = credentials.get('developer_token')
                web_credentials['use_proto_plus'] = credentials.get('use_proto_plus', True)
            else:
                web_credentials = credentials

            options = [
                discord.SelectOption(
                    label="Add to existing campaign",
                    value="existing",
                    description="Add your ad to an existing campaign you have"
                ),
                discord.SelectOption(
                    label="Create a new campaign",
                    value="new",
                    description="Create a new campaign for your ad"
                )
            ]
            
            select_menu = discord.ui.Select(
                placeholder="Choose an option",
                options=options
            )

            async def select_callback(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True)
                data = {
                    "customer_id": customer_id,
                    "credentials": web_credentials
                }
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post('https://googleadsapicalls.onrender.com/authenticate', json=data) as response:
                            if response.status == 200:
                                result_text = await response.text()
                                try: 
                                    result = json.loads(result_text)
                                except json.JSONDecodeError:
                                    await interaction.followup.send(f"Unexpected response format: {result_text}", ephemeral=True)
                                    return
                                if "refresh_token" in result:
                                    await interaction.followup.send("Authentication successful. Proceeding to get campaigns, please wait...", ephemeral=True)
                                    if isinstance(result, str):
                                        try:
                                            result = json.loads(result)
                                        except json.JSONDecodeError:
                                            await interaction.followup.send("Error: Invalid authentication response format", ephemeral=True)
                                            return
                                        
                                    complete_credentials = {
                                        **result,
                                        "developer_token": web_credentials.get("developer_token"),
                                        "scopes": ['https://www.googleapis.com/auth/adwords']
                                    }
                                    if select_menu.values[0] == "existing":
                                        await get_campaigns(interaction, customer_id, complete_credentials, business_name)
                                    else:
                                        await create_campaign_flow(interaction, customer_id, complete_credentials)
                                elif "auth_url" in result and "state" in result:
                                    auth_url = result["auth_url"]
                                    state = result["state"]
                                    view = AuthCompletedView(auth_url, state, credentials['client_id'], customer_id, web_credentials)
                                    await interaction.followup.send(
                                        f"Please authorize access to your Google Ads using this link: {auth_url}\n"
                                        "After authorization, click the 'Completed Authorization' button below.",
                                        view=view,
                                        ephemeral=True
                                    )
                                else:
                                    await interaction.followup.send("Unexpected authentication response. Please try again.", ephemeral=True)
                            else:
                                error_details = await response.text()
                                await interaction.followup.send(f"Error: Received status code {response.status} from authentication server. Details: {error_details}", ephemeral=True)
                except aiohttp.ClientError as e:
                    await interaction.followup.send(f"Error communicating with server: {str(e)}", ephemeral=True)
            select_menu.callback = select_callback
            view = discord.ui.View()
            view.add_item(select_menu)
            await interaction.followup.send("Please select an option:", view=view)
        else:
            await interaction.response.send_message("Unable to find your business name. Please make sure you've completed the initial setup.", ephemeral=True)
    else:
        calendly_link = "https://calendly.com/emmanuel-emmanuelsibanda/30min"
        await interaction.response.send_message(
            f"You don't have access to this command yet. Please complete the onboarding process by scheduling a call: {calendly_link}",
            ephemeral=True
        )

client.run(os.getenv('DISCORD_TOKEN'))
