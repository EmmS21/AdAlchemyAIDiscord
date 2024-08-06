import discord
from discord import app_commands, ButtonStyle, Embed, File
from discord.ui import Button, View, TextInput, Modal
from collections import defaultdict
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection

guild_business_data = defaultdict(dict)
guild_states = {}

class ConfirmPricing(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction):
        guild = interaction.guild
        owner = guild.owner

        business_name = guild_business_data[self.guild_id].get('business_name')
        website_link = guild_business_data[self.guild_id].get('website_link')

        await interaction.response.send_message("You have consented to the pricing model. Great! You can now use the /keywords command to start selecting keywords for your campaign.")
        await interaction.channel.send(f"A mapping has been made between your ID: {owner.id} and your business {business_name}")
        
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        onboarding_db_name = "onboarding_agent"
        onboarding_collection_name = business_name
        mappings_db_name = "mappings"
        mappings_collection_name = "companies"

        onboarding_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, onboarding_db_name, onboarding_collection_name)
        mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, mappings_db_name, mappings_collection_name)

        business_data = {
            "business": business_name,
            "website": website_link
        }

        onboarding_collection.update_one({}, {"$set": business_data}, upsert=True)
        
        mappings_collection.update_one(
            {"owner_id": owner.id},
            {"$set": {"business_name": business_name}},
            upsert=True
        )

        embed = discord.Embed(
            title="Let's book some time to complete your onboarding and chat more about your business",
            description="Click the link below to schedule an appointment with us:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Calendly Scheduling",
            value="[Schedule Appointment](https://calendly.com/emmanuel-emmanuelsibanda/30min)",
            inline=False
        )

        await interaction.channel.send(embed=embed)

        guild_states[self.guild_id] = "setup_complete"
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction):
        await interaction.response.send_message("You have not consented to the pricing model. If you have any questions or concerns, please reach out to our support team.")
        guild_states[self.guild_id] = "setup_complete"
        self.stop()
