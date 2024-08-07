from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
from Helpers.helperfuncs import website_exists_in_db
from Helpers.helperClasses import ConfirmPricing
import discord
from discord import app_commands
import os
# import dotenv
from collections import defaultdict
import re
from pathlib import Path

# dotenv.load_dotenv()
guild_business_data = defaultdict(dict)

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

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    await sync_commands()

@client.event
async def on_guild_join(guild):
    CONNECTION_STRING = os.getenv("CONNECTION_STRING")
    print('connection', CONNECTION_STRING)
    mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")

    owner_id = guild.owner_id
    owner_record = mappings_collection.find_one({"owner_id": owner_id})

    if owner_record:
        business_name = owner_record.get("business_name", "valued business")
        welcome_back_message = f"Welcome back {business_name}!"
        calendly_message = "Please schedule a date to complete your onboarding and discuss your business needs: [Calendly Link](https://calendly.com/emmanuel-emmanuelsibanda/30min)"

        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(welcome_back_message)
                await channel.send(calendly_message)
                break
    else:
        welcome_message = """
        Hello everyone! I am AdAlchemyAI, a bot to help you run your digital marketing. I look at your site to understand what your business does, I do this by going to your website, extracting information about your business, your users and what you do. 
        
        After this I will browse the internet as though I am your users, getting keywords people would likely use to show intent to interact with your business. 
        
        I use this and other tools to get the best keywords for you. You can approve the keywords you would like me to use by using the /keywords slash command, you can also edit the ad text I create for you using /adtext slash command.
        
        I will only use the keywords and adtext you approved to run your ads. I will ask you to set a daily budget for your campaign using /setcampaignbudget. I will not let you run ads without you setting your budget first
        
        I will only run ads when you manually trigger this process using /runads. Ok, let's start the onboarding process. Remember you can always use /help to see what commands you can use.

        """
        first_question = "What is the name of your business?"
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send(welcome_message)
                    await channel.send(first_question)
                    guild_states[guild.id] = "waiting_for_business_name"
                    break
                except Exception as e:
                    print(f"An error occurred while sending a welcome message to {guild.name} in {channel.name}: {e}")
                    break

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    guild_id = message.guild.id
    current_state = guild_states.get(guild_id)

    CONNECTION_STRING = os.getenv("CONNECTION_STRING")

    if current_state == "waiting_for_business_name":
        business_name = message.content.lower()
        onboarding_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "onboarding_agent", business_name)
        
        try:
            collection_exists = onboarding_collection.estimated_document_count() > 0
        except Exception as e:
            collection_exists = False

        if collection_exists:
            await message.channel.send(f"'{business_name}' already exists, please select a unique business name.")
            return
        
        guild_business_data[guild_id]['business_name'] = business_name
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
            onboarding_agent_db = connect_to_mongo_and_get_collection(CONNECTION_STRING, "onboarding_agent", None)
            
            if onboarding_agent_db and website_exists_in_db(onboarding_agent_db, website_link):
                await message.channel.send(f"'{website_link}' already exists, please enter a unique website.")
                return

            guild_business_data[guild_id]['website_link'] = website_link
            
            embed = discord.Embed(title="Pricing Model Breakdown", color=discord.Color.blue())
            embed.add_field(name="Daily Budget", value="0-$100\n$100 - $1000\n>$1000", inline=True)
            embed.add_field(name="Fee", value="25%\n20%\n15%", inline=True)
           
            await message.channel.send("Here's a breakdown of our pricing model:", embed=embed)
            
            view = ConfirmPricing(guild_id)
            await message.channel.send("Do you consent to this pricing model?", view=view)
            guild_states[guild_id] = "waiting_for_consent"
        else:
            await message.channel.send("That doesn't appear to be a valid URL. Please enter a valid website URL (e.g., https://www.example.com):")

class HelpView(discord.ui.View):
    def __init__(self, pages):
        super().__init__(timeout=300) 
        self.pages = pages
        self.current_page = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(content=self.pages[self.current_page], view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
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

client.run(os.getenv('DISCORD_TOKEN'))
