import discord
from discord import ButtonStyle, Embed
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

from discord import ButtonStyle, Embed, TextStyle
from discord.ui import View, Button, Modal, TextInput
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
import os

class AddPathModal(Modal, title='Add New Research Path'):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.path = TextInput(label='New Research Path', style=TextStyle.paragraph, placeholder='Enter the new research path here...', required=True, max_length=1000)
        self.add_item(self.path)

    async def on_submit(self, interaction):
        await self.callback(interaction, self.path.value)

class ResearchPathsView(View):
    def __init__(self, paths, business_name):
        super().__init__()
        self.paths = paths
        self.business_name = business_name
        self.current_page = 0
        self.per_page = 5
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        previous_button = Button(label="Previous", style=ButtonStyle.gray, disabled=(self.current_page == 0))
        previous_button.callback = self.previous_callback
        self.add_item(previous_button)

        next_button = Button(label="Next", style=ButtonStyle.gray, disabled=(self.current_page >= (len(self.paths) - 1) // self.per_page))
        next_button.callback = self.next_callback
        self.add_item(next_button)

        add_button = Button(label="Add Path", style=ButtonStyle.green)
        add_button.callback = self.add_path_callback
        self.add_item(add_button)

    async def previous_callback(self, interaction):
        self.current_page = max(0, self.current_page - 1)
        await self.update_message(interaction)

    async def next_callback(self, interaction):
        self.current_page = min((len(self.paths) - 1) // self.per_page, self.current_page + 1)
        await self.update_message(interaction)

    async def add_path_callback(self, interaction):
        modal = AddPathModal(self.add_path)
        await interaction.response.send_modal(modal)

    async def add_path(self, interaction, new_path):
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        business_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "marketing_agent", self.business_name.lower())
        
        if business_collection:
            result = business_collection.update_one(
                {},
                {"$push": {"list_of_paths_taken": new_path}},
                upsert=True
            )
            
            if result.modified_count > 0 or result.upserted_id:
                self.paths.append(new_path)
                await interaction.response.send_message("New research path added successfully!", ephemeral=True)
                await self.update_message(interaction)
            else:
                await interaction.response.send_message("Failed to add new research path.", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to connect to the database.", ephemeral=True)

    async def update_message(self, interaction):
        embed = self.get_embed()
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    def get_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        current_paths = self.paths[start:end]

        embed = Embed(title="Research Paths", color=discord.Color.blue())
        for i, path in enumerate(current_paths, start=start+1):
            embed.add_field(name=f"Path {i}", value=path, inline=False)
        embed.set_footer(text=f"Page {self.current_page + 1} of {(len(self.paths) - 1) // self.per_page + 1}")
        return embed
    
class UserPersonaView(View):
    def __init__(self, personas, business_name):
        super().__init__()
        self.personas = personas if isinstance(personas, list) else [personas]
        self.business_name = business_name
        self.current_page = 0
        self.per_page = 1 

        self.previous_button = Button(label="Previous", style=ButtonStyle.grey, disabled=True)
        self.next_button = Button(label="Next", style=ButtonStyle.grey)
        self.add_button = Button(label="Add Persona", style=ButtonStyle.green)
        self.edit_button = Button(label="Edit Persona", style=ButtonStyle.primary)  # Changed from blue to primary
        self.delete_button = Button(label="Delete Persona", style=ButtonStyle.red)
        
        self.previous_button.callback = self.previous_callback
        self.next_button.callback = self.next_callback
        self.add_button.callback = self.add_callback
        self.edit_button.callback = self.edit_callback
        self.delete_button.callback = self.delete_callback
        
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.add_item(self.add_button)
        self.add_item(self.edit_button)
        self.add_item(self.delete_button)

    async def previous_callback(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        await self.update_message(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        self.current_page = min(len(self.personas) - 1, self.current_page + 1)
        await self.update_message(interaction)

    async def add_callback(self, interaction: discord.Interaction):
        modal = PersonaModal(self.add_persona, title="Add New Persona")
        await interaction.response.send_modal(modal)

    async def edit_callback(self, interaction: discord.Interaction):
        current_persona = self.personas[self.current_page]
        modal = PersonaModal(self.edit_persona, title="Edit Persona", default_values=current_persona)
        await interaction.response.send_modal(modal)

    async def delete_callback(self, interaction: discord.Interaction):
        await self.delete_persona(interaction)

    async def update_message(self, interaction):
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.personas) - 1)
        self.edit_button.disabled = (len(self.personas) == 0)
        self.delete_button.disabled = (len(self.personas) == 0)
        
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def get_embed(self):
        if not self.personas:
            return discord.Embed(title="User Personas", description="No personas found. Add a new one!", color=discord.Color.blue())
        
        persona = self.personas[self.current_page]
        embed = discord.Embed(title=f"User Persona {self.current_page + 1}", color=discord.Color.blue())
        
        if isinstance(persona, dict):
            for key, value in persona.items():
                embed.add_field(name=key.capitalize(), value=value, inline=False)
        else:
            embed.add_field(name="Description", value=persona, inline=False)
        
        embed.set_footer(text=f"Persona {self.current_page + 1} of {len(self.personas)}")
        return embed


    async def add_persona(self, interaction: discord.Interaction, persona_data: dict):
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        business_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "marketing_agent", self.business_name.lower())
        
        if business_collection:
            result = business_collection.update_one(
                {},
                {"$push": {"user_personas": persona_data}},
                upsert=True
            )
            
            if result.modified_count > 0 or result.upserted_id:
                self.personas.append(persona_data)
                self.current_page = len(self.personas) - 1
                await interaction.response.send_message("New persona added successfully!", ephemeral=True)
                await self.update_message(interaction)
            else:
                await interaction.response.send_message("Failed to add new persona.", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to connect to the database.", ephemeral=True)

    async def edit_persona(self, interaction: discord.Interaction, persona_data: dict):
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        business_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "marketing_agent", self.business_name.lower())
        
        if business_collection:
            result = business_collection.update_one(
                {},
                {"$set": {f"user_personas.{self.current_page}": persona_data}}
            )
            
            if result.modified_count > 0:
                self.personas[self.current_page] = persona_data
                await interaction.response.send_message("Persona updated successfully!", ephemeral=True)
                await self.update_message(interaction)
            else:
                await interaction.response.send_message("Failed to update persona.", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to connect to the database.", ephemeral=True)

    async def delete_persona(self, interaction: discord.Interaction):
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        business_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "marketing_agent", self.business_name.lower())
        
        if business_collection:
            result = business_collection.update_one(
                {},
                {"$pull": {"user_personas": self.personas[self.current_page]}}
            )
            
            if result.modified_count > 0:
                del self.personas[self.current_page]
                self.current_page = max(0, self.current_page - 1)
                await interaction.response.send_message("Persona deleted successfully!", ephemeral=True)
                await self.update_message(interaction)
            else:
                await interaction.response.send_message("Failed to delete persona.", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to connect to the database.", ephemeral=True)

class PersonaModal(Modal):
    def __init__(self, callback, title="Persona", default_values=None):
        super().__init__(title=title)
        self.callback = callback
        self.add_item(TextInput(label="Title", style=TextStyle.short, placeholder="E.g., Finance Bro Changing Careers to Software Engineering", required=True, 
                                default=default_values.get('title', '') if default_values else ''))
        self.add_item(TextInput(label="Demographics", style=TextStyle.paragraph, placeholder="Age, gender, current role, education, location", required=True,
                                default=default_values.get('demographics', '') if default_values else ''))
        self.add_item(TextInput(label="Motivation", style=TextStyle.paragraph, placeholder="Reasons for career change", required=True,
                                default=default_values.get('motivation', '') if default_values else ''))
        self.add_item(TextInput(label="Pain Points", style=TextStyle.paragraph, placeholder="Challenges and concerns", required=True,
                                default=default_values.get('pain_points', '') if default_values else ''))
        self.add_item(TextInput(label="Goals and Preferences", style=TextStyle.paragraph, placeholder="Career goals and learning preferences", required=True,
                                default=default_values.get('goals', '') + '\n' + default_values.get('preferences', '') if default_values else ''))

    async def on_submit(self, interaction: discord.Interaction):
        goals_and_preferences = self.children[4].value.split('\n', 1)
        persona_data = {
            'title': self.children[0].value,
            'demographics': self.children[1].value,
            'motivation': self.children[2].value,
            'pain_points': self.children[3].value,
            'goals': goals_and_preferences[0],
            'preferences': goals_and_preferences[1] if len(goals_and_preferences) > 1 else ''
        }
        await self.callback(interaction, persona_data)

