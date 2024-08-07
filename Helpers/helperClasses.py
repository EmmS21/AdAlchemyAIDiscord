import discord
from discord import app_commands, ButtonStyle, Embed, File
from discord.ui import Button, View, TextInput, Modal
from collections import defaultdict
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
import os

guild_business_data = defaultdict(dict)
guild_states = {}

class ConfirmPricing(discord.ui.View):
    def __init__(self, guild_id, business_name, website_link):
        super().__init__()
        self.guild_id = guild_id
        self.business_name = business_name
        self.website_link = website_link

        self.is_second_chance = False

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_yes_response(interaction)

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_second_chance:
            self.is_second_chance = True
            await interaction.response.send_message("Are you sure? You can still join our waiting list or exit the conversation.", view=self)
        else:
            await interaction.response.send_message("If you would like to restart the process, add the bot to a new server. Alternatively, feel free to email emmanuel@emmanuelsibanda.com if you have any questions.")
            guild_states[self.guild_id] = "conversation_ended"
            self.stop()

    async def handle_yes_response(self, interaction: discord.Interaction):
        guild = interaction.guild
        owner = guild.owner

        await interaction.response.send_message(f"A mapping has been made between your Discord ID: {owner.id} and your business {self.business_name}. This helps us remember you")
        
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")

        if not CONNECTION_STRING:
            await interaction.followup.send("Error: Database connection string is not set. Please contact support.")
            return

        onboarding_db_name = "onboarding_agent"
        onboarding_collection_name = self.business_name
        mappings_db_name = "mappings"
        mappings_collection_name = "companies"

        try:
            onboarding_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, onboarding_db_name, onboarding_collection_name)
            mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, mappings_db_name, mappings_collection_name)

            if onboarding_collection is None or mappings_collection is None:
                await interaction.followup.send("Error: Unable to connect to the database. Please try again later or contact support.")
                return

            business_data = {
                "business": self.business_name,
                "website": self.website_link
            }

            onboarding_collection.update_one({}, {"$set": business_data}, upsert=True)
        
            mappings_collection.update_one(
                {"owner_id": owner.id},
                {"$set": {"business_name": self.business_name}},
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

            await interaction.followup.send(embed=embed)

            guild_states[self.guild_id] = "setup_complete"
            self.stop()

        except Exception as e:
            error_message = f"An error occurred while processing your request: {str(e)}"
            await interaction.followup.send(error_message)
            print(error_message) 