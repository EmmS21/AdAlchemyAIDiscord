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

class BusinessView(View):
    def __init__(self, business_data):
        super().__init__()
        self.business_data = business_data
        self.current_page = 0
        self.per_page = 1000  

        self.previous_button = Button(label="Previous", style=ButtonStyle.gray, disabled=True)
        self.next_button = Button(label="Next", style=ButtonStyle.gray)
        self.edit_button = Button(label="Edit", style=ButtonStyle.primary)
        
        self.previous_button.callback = self.previous_callback
        self.next_button.callback = self.next_callback
        self.edit_button.callback = self.edit_callback

        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.add_item(self.edit_button)

    async def previous_callback(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        await self.update_message(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        self.current_page = min((len(self.business_data) - 1) // self.per_page, self.current_page + 1)
        await self.update_message(interaction)

    async def edit_callback(self, interaction: discord.Interaction):
        modal = BusinessEditModal(self.business_data)
        await interaction.response.send_modal(modal)

    async def update_message(self, interaction):
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == (len(self.business_data) - 1) // self.per_page)
        
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def get_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        current_data = self.business_data[start:end]

        embed = Embed(title="Business Information", color=discord.Color.blue())
        embed.add_field(name="Data", value=current_data, inline=False)
        embed.set_footer(text=f"Page {self.current_page + 1} of {(len(self.business_data) - 1) // self.per_page + 1}")
        return embed

class BusinessEditModal(Modal, title='Edit Business Information'):
    def __init__(self, business_data):
        super().__init__()
        self.business_info = TextInput(
            label='Business Information',
            style=discord.TextStyle.paragraph,
            placeholder='Enter the business information here...',
            default=business_data,
            required=True,
            max_length=4000
        )
        self.add_item(self.business_info)

    async def on_submit(self, interaction: discord.Interaction):
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
        user_record = mappings_collection.find_one({"owner_ids": interaction.user.id})
        
        if user_record and "business_name" in user_record:
            business_name = user_record["business_name"]
            collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "marketing_agent", business_name.lower())
            
            result = collection.update_one(
                {},
                {"$set": {"business": self.business_info.value}},
                upsert=True
            )

            if result.modified_count > 0 or result.upserted_id:
                await interaction.response.send_message(f"Business information updated successfully!", ephemeral=True)
            else:
                await interaction.response.send_message(f"Failed to update business information.", ephemeral=True)
        else:
            await interaction.response.send_message("Unable to find your business. Please make sure you've completed the initial setup.", ephemeral=True)