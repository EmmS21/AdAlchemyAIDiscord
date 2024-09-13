from datetime import datetime
import aiohttp
import discord
from discord import ButtonStyle, Embed, TextStyle
from discord.ui import Button, View, TextInput, Modal
from collections import defaultdict
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
import Helpers.helperfuncs as helperfuncs
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
        
        if business_collection is not None:
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
        
        if business_collection is not None:
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

class KeywordPaginationView(discord.ui.View):
    def __init__(self, selected_keywords, new_keywords, collection, title, last_update):
        super().__init__()
        self.selected_keywords = self._normalize_keywords(selected_keywords)
        self.new_keywords = self._normalize_keywords(new_keywords)
        self.collection = collection
        self.current_page = 0
        self.per_page = 5
        self.current_keyword_type = "selected"
        self.last_update = last_update 


        self.selected_keywords_dict = {}  
        latest_document = helperfuncs.get_latest_document(self.collection)
        if latest_document and 'selected_keywords' in latest_document:
            self.selected_keywords = self._normalize_keywords(latest_document['selected_keywords'])
        
        self.selected_keywords_dict = {kw['text']: kw for kw in self.selected_keywords}

        # Create persistent buttons
        self.previous_button = discord.ui.Button(label="Previous", style=ButtonStyle.gray, disabled=True)
        self.next_button = discord.ui.Button(label="Next", style=ButtonStyle.gray)
        self.submit_button = discord.ui.Button(label="Submit", style=ButtonStyle.blurple)
        
        # Add button callbacks
        self.previous_button.callback = self.previous_callback
        self.next_button.callback = self.next_callback
        self.submit_button.callback = self.submit_callback

         # Create select menu for keyword type
        self.keyword_type_select = discord.ui.Select(
            placeholder="Choose Keyword Category",
            options=[
                discord.SelectOption(label="Previously Selected Keywords", value="selected"),
                discord.SelectOption(label="New Keywords", value="new")
            ]
        )
        self.keyword_type_select.callback = self.keyword_type_callback
        
        # Add persistent buttons to the view
        self.add_item(self.keyword_type_select)
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.add_item(self.submit_button)
        self.add_toggle_buttons()

    async def previous_callback(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        await self.update_message(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        keywords = self.selected_keywords if self.current_keyword_type == "selected" else self.new_keywords
        self.current_page = min(len(keywords) // self.per_page, self.current_page + 1)
        await self.update_message(interaction)

    async def submit_callback(self, interaction: discord.Interaction):
        selected_keywords_list = list(self.selected_keywords_dict.values())
        latest_document = helperfuncs.get_latest_document(self.collection)
        if latest_document:
            result = self.collection.update_one(
                {'_id': latest_document['_id']},
                {"$set": {"selected_keywords": selected_keywords_list}}
            )
            if result.modified_count > 0:
                await interaction.response.send_message(f"Selected keywords have been saved to the latest document in the database.", ephemeral=True)
            else:
                await interaction.response.send_message(f"No changes were made to the database.", ephemeral=True)
        else:
            result = self.collection.insert_one({"selected_keywords": selected_keywords_list})
            if result.inserted_id:
                await interaction.response.send_message(f"Selected keywords have been saved to a new document in the database.", ephemeral=True)
            else:
                await interaction.response.send_message(f"Failed to save keywords to the database.", ephemeral=True)        
        self.stop()
    
    async def keyword_type_callback(self, interaction: discord.Interaction):
        self.current_keyword_type = self.keyword_type_select.values[0]
        self.current_page = 0
        await self.update_message(interaction)

    def add_toggle_buttons(self):
        keywords = self.selected_keywords if self.current_keyword_type == "selected" else self.new_keywords
        start = self.current_page * self.per_page
        end = start + self.per_page
        for i in range(start, min(end, len(keywords))):
            self.add_item(discord.ui.Button(style=ButtonStyle.gray, label=f"Toggle {i+1-start}", custom_id=f"toggle_{i}"))

    def _normalize_keywords(self, keywords):
        if isinstance(keywords, dict):
            return [{'text': k, **v} for k, v in keywords.items()]
        elif isinstance(keywords, list):
            return [{'text': kw} if isinstance(kw, str) else kw for kw in keywords]
        else:
            raise ValueError("Invalid keyword format")

    async def update_message(self, interaction):
        self.clear_items()
        
        self.add_item(self.keyword_type_select)
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.add_item(self.submit_button)
        
        keywords = self.selected_keywords if self.current_keyword_type == "selected" else self.new_keywords
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(keywords) // self.per_page)
        
        self.add_toggle_buttons()
        
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def get_embed(self):
        keywords = self.selected_keywords if self.current_keyword_type == "selected" else self.new_keywords
        start = self.current_page * self.per_page
        end = start + self.per_page
        
        if isinstance(keywords, dict):
            keywords_list = list(keywords.items())
        else:
            keywords_list = keywords
        
        current_keywords = keywords_list[start:end]

        title = "Previously Selected Keywords" if self.current_keyword_type == "selected" else "New Keywords"
        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.description = "Use the menu above to switch between keyword categories."

        for keyword in current_keywords:
            if isinstance(keyword, tuple): 
                key, value = keyword
                status = "✅" if key in self.selected_keywords_dict else "❌"
                embed.add_field(name=f"{key} [{status}]", value=str(value), inline=False)
            elif isinstance(keyword, dict) and 'text' in keyword:
                status = "✅" if keyword['text'] in self.selected_keywords_dict else "❌"
                value = f"Avg. Monthly Searches: {keyword.get('avg_monthly_searches', 'N/A')}\nCompetition: {keyword.get('competition', 'N/A')}"
                if self.current_keyword_type == "new":
                    value += f"\nLast Update: {self.last_update}"  
                embed.add_field(name=f"{keyword['text']} [{status}]", value=value, inline=False)
            elif isinstance(keyword, str):
                status = "✅" if keyword in self.selected_keywords_dict else "❌"
                embed.add_field(name=f"{keyword} [{status}]", value="Previously selected keyword", inline=False)

        total_pages = (len(keywords_list) - 1) // self.per_page + 1
        embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages}")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.data['custom_id'].startswith('toggle_'):
                index = int(interaction.data['custom_id'].split('_')[1])
                keywords = self.selected_keywords if self.current_keyword_type == "selected" else self.new_keywords
                
                # Convert keywords to a list if it's a dictionary
                if isinstance(keywords, dict):
                    keywords_list = list(keywords.items())
                else:
                    keywords_list = keywords
                
                if index < len(keywords_list):
                    keyword = keywords_list[index]
                    
                    if isinstance(keyword, tuple):  
                        keyword_text = keyword[0]
                        keyword_data = keyword[1]
                    elif isinstance(keyword, dict) and 'text' in keyword:
                        keyword_text = keyword['text']
                        keyword_data = keyword
                    elif isinstance(keyword, str):
                        keyword_text = keyword
                        keyword_data = {'text': keyword}
                    else:
                        return False 
                    
                    if keyword_text in self.selected_keywords_dict:
                        del self.selected_keywords_dict[keyword_text]
                    else:
                        self.selected_keywords_dict[keyword_text] = {
                            'text': keyword_text,
                            'avg_monthly_searches': keyword_data.get('avg_monthly_searches', 'N/A'),
                            'competition': keyword_data.get('competition', 'N/A')
                        }
                    
                    await self.update_message(interaction)
                return False
            return True 
     
class AdTextView(View):
    def __init__(self, ad_variations, finalized_ad_texts, collection, last_update):
        super().__init__()
        self.ad_variations = ad_variations
        self.headlines = [variation['headlines'] for variation in ad_variations]
        self.descriptions = [variation['descriptions'] for variation in ad_variations]
        self.finalized_ad_texts = finalized_ad_texts
        self.collection = collection
        self.last_update = last_update
        self.current_page = 0
        self.total_ads = min(len(self.headlines), len(self.descriptions))
        self.current_type = "new" 
        
        self.previous_button = Button(style=ButtonStyle.gray, disabled=True)
        self.previous_button.label = "Previous"
        self.next_button = Button(style=ButtonStyle.gray)
        self.next_button.label = "Next"
        self.edit_button = Button(style=ButtonStyle.primary)
        self.edit_button.label = "Edit"
        self.delete_button = Button(style=ButtonStyle.danger)
        self.delete_button.label = "Delete Ad"
        
        self.previous_button.callback = self.previous_callback
        self.next_button.callback = self.next_callback
        self.edit_button.callback = self.edit_callback
        self.delete_button.callback = self.delete_callback

        # Create select menu for ad text type
        self.ad_type_select = discord.ui.Select(
            placeholder="Choose Ad Text Type",
            options=[
                discord.SelectOption(label="New Ad Text", value="new"),
                discord.SelectOption(label="Finalized Ad Text", value="finalized")
            ]
        )
        self.ad_type_select.callback = self.ad_type_callback

        self.add_item(self.ad_type_select)
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.add_item(self.edit_button)
        self.add_item(self.delete_button)

    async def delete_callback(self, interaction: discord.Interaction):
        confirm_button = Button(style=ButtonStyle.danger, label="Confirm Delete")
        cancel_button = Button(style=ButtonStyle.secondary, label="Cancel")

        async def confirm_delete(confirm_interaction: discord.Interaction):
            await self.perform_delete(confirm_interaction)

        async def cancel_delete(cancel_interaction: discord.Interaction):
            await cancel_interaction.response.edit_message(content="Deletion cancelled.", view=None)

        confirm_button.callback = confirm_delete
        cancel_button.callback = cancel_delete

        confirm_view = View()
        confirm_view.add_item(confirm_button)
        confirm_view.add_item(cancel_button)

        await interaction.response.send_message("Are you sure you want to delete this ad?", view=confirm_view, ephemeral=True)

    async def perform_delete(self, interaction: discord.Interaction):
        try:
            latest_document = helperfuncs.get_latest_document(self.collection)
            if not latest_document:
                await interaction.response.send_message("No document found to delete from.", ephemeral=True)
                return

            if self.current_type == "new":
                # Delete from ad_variations
                update = {"$pull": {"ad_variations": {"headline": self.headlines[self.current_page]}}}
                result = self.collection.update_one({'_id': latest_document['_id']}, update)
                
                if result.modified_count > 0:
                    del self.ad_variations[self.current_page]
                    del self.headlines[self.current_page]
                    del self.descriptions[self.current_page]
                    self.total_ads -= 1
            else:
                # Delete from finalized_ad_text
                update = {"$pull": {"finalized_ad_text": {"index": self.current_page}}}
                result = self.collection.update_one({'_id': latest_document['_id']}, update)
                
                if result.modified_count > 0:
                    self.finalized_ad_texts = [ad for ad in self.finalized_ad_texts if ad['index'] != self.current_page]

            if result.modified_count > 0:
                await interaction.response.edit_message(content="Ad successfully deleted.", view=None)
                self.current_page = max(0, min(self.current_page, self.total_ads - 1))
                await self.update_parent_message(interaction)
            else:
                await interaction.response.edit_message(content="Failed to delete the ad. No changes were made.", view=None)

        except Exception as e:
            await interaction.response.edit_message(content=f"An error occurred while deleting the ad: {str(e)}", view=None)

    async def update_parent_message(self, interaction: discord.Interaction):
        embed = self.get_embed()
        await interaction.message.edit(embed=embed, view=self)

    async def ad_type_callback(self, interaction: discord.Interaction):
        self.current_type = self.ad_type_select.values[0]
        self.current_page = 0
        await self.update_message(interaction)

    async def previous_callback(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        await self.update_message(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        self.current_page = min(self.total_ads - 1, self.current_page + 1)
        await self.update_message(interaction)

    async def edit_callback(self, interaction: discord.Interaction):
        try:
            headline = self.headlines[self.current_page]
            description = self.descriptions[self.current_page]
            
            finalized_ad = next((fad for fad in self.finalized_ad_texts if fad.get('index') == self.current_page), None)
            is_finalized = finalized_ad is not None
            if finalized_ad:
                headline = finalized_ad['headline']
                description = finalized_ad['description']
            
            modal = AdEditModal(headline, description, self.current_page, self.collection, self, is_finalized)
            await interaction.response.send_modal(modal)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred while opening the edit modal: {str(e)}", ephemeral=True)

    async def update_message(self, interaction):
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == self.total_ads - 1)
        
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def get_embed(self):
        if self.current_type == "new":
            title = f"Ad Variation {self.current_page + 1}"
            if self.current_page < len(self.ad_variations):
                current_variation = self.ad_variations[self.current_page]
                headlines = current_variation['headlines']
                descriptions = current_variation['descriptions']                
                headline = headlines[self.current_subindex % len(headlines)]
                description = descriptions[self.current_subindex % len(descriptions)]            
                footer_text = f"Ad {self.current_page + 1} of {self.total_ads} | Last Update: {self.last_update}"
            else: 
                headline = "No headline"
                description = "No description"
                footer_text = f"Ad {self.current_page + 1} of {self.total_ads} | Last Update: {self.last_update}"
        else:
            finalized_ad = next((fad for fad in self.finalized_ad_texts if fad['index'] == self.current_page), None)
            if finalized_ad:
                title = f"Finalized Ad Variation {self.current_page + 1}"
                if self.current_page < len(self.ad_variations):
                    current_variation = self.ad_variations[self.current_page]
                    headlines = current_variation['headlines']
                    descriptions = current_variation['descriptions']
                    headline = headlines[self.current_subindex % len(headlines)]
                    description = descriptions[self.current_subindex % len(descriptions)]
                    footer_text = f"Ad {self.current_page + 1} of {self.total_ads} | Variation {self.current_subindex + 1} of {len(headlines)}"
                else:
                    headline = 'No headline'
                    description = 'No description'
                    footer_text = f"Ad {self.current_page + 1} of {self.total_ads}"

        embed = Embed(title=title, color=discord.Color.blue())
        embed.add_field(name="Headline", value=headline, inline=False)
        embed.add_field(name="Description", value=description, inline=False)
        embed.set_footer(text=footer_text)
        return embed
    
class AdEditModal(Modal):
    def __init__(self, headline, description, index, collection, view, is_finalized=False):
        super().__init__(title='Edit Ad Text')
        self.index = index
        self.collection = collection
        self.view = view
        self.is_finalized = is_finalized

        self.warning = TextInput(
            label='Warning (do not edit)',
            style=TextStyle.short,
            default=self.get_warning_text(headline, description),
            required=False,
            max_length=100
        )

        self.headline = TextInput(
            label='Headline (max 30 characters)',
            style=TextStyle.short,
            default=headline,
            required=True,
            max_length=200  
        )

        self.description = TextInput(
            label='Description (max 90 characters)',
            style=TextStyle.paragraph,
            default=description,
            required=True,
            max_length=200  
        )

        self.add_item(self.warning)
        self.add_item(self.headline)
        self.add_item(self.description)

    def get_warning_text(self, headline, description):
        warnings = []
        if len(headline) > 30:
            warnings.append(f"Headline exceeds limit by {len(headline) - 30} characters")
        if len(description) > 90:
            warnings.append(f"Description exceeds limit by {len(description) - 90} characters")
        return " | ".join(warnings) if warnings else "No warnings"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_headline = self.headline.value
            new_description = self.description.value

            warning_text = self.get_warning_text(new_headline, new_description)
            
            errors = []
            if len(new_headline) > 30:
                errors.append(f"Headline exceeds 30 characters (current: {len(new_headline)})")
            if len(new_description) > 90:
                errors.append(f"Description exceeds 90 characters (current: {len(new_description)})")

            if errors:
                error_message = "Cannot save ad text. Please correct the following:\n" + "\n".join(errors)
                await interaction.response.send_message(error_message, ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            new_finalized_ad = {
                'index': self.index,
                'headline': new_headline,
                'description': new_description
            }

            latest_document = helperfuncs.get_latest_document(self.collection)

            if latest_document:
                if 'finalized_ad_text' not in latest_document or not isinstance(latest_document['finalized_ad_text'], list):
                    update = {"$set": {"finalized_ad_text": [new_finalized_ad]}}
                else:
                    existing_finalized_ads = [ad for ad in latest_document['finalized_ad_text'] if ad.get('index') != self.index]
                    existing_finalized_ads.append(new_finalized_ad)
                    update = {"$set": {"finalized_ad_text": existing_finalized_ads}}

                result = self.collection.update_one({'_id': latest_document['_id']}, update)

                if result.modified_count > 0:
                    self.view.finalized_ad_texts = [fad for fad in self.view.finalized_ad_texts if fad.get('index') != self.index]
                    self.view.finalized_ad_texts.append(new_finalized_ad)
                    
                    embed = self.view.get_embed()
                    await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self.view)
                    await interaction.followup.send(f"Ad {self.index + 1} finalized and saved to the database successfully!", ephemeral=True)
                else:
                    await interaction.followup.send("No changes were made to the database.", ephemeral=True)
            else:
                new_document = {
                    "finalized_ad_text": [new_finalized_ad]
                }
                result = self.collection.insert_one(new_document)
                if result.inserted_id:
                    self.view.finalized_ad_texts.append(new_finalized_ad)
                    embed = self.view.get_embed()
                    await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self.view)
                    await interaction.followup.send(f"Ad {self.index + 1} finalized and saved to a new document in the database.", ephemeral=True)
                else:
                    await interaction.followup.send(f"Failed to save ad to the database.", ephemeral=True)

            if warning_text != "No warnings":
                await interaction.followup.send(f"Warning: {warning_text}. Changes have been saved, but may be truncated in some displays.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

class AuthCompletedView(discord.ui.View):
    def __init__(self, auth_url, state, client_id, customer_id, credentials):
        super().__init__()
        self.auth_url = auth_url
        self.state = state
        self.client_id = client_id
        self.customer_id = customer_id
        self.credentials = credentials
        self.refresh_token = None

    @discord.ui.button(label="Completed Authorization", style=discord.ButtonStyle.green)
    async def auth_completed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
        mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
        user_record = mappings_collection.find_one({"owner_ids": interaction.user.id})
        if user_record and "business_name" in user_record:
            business_name = user_record["business_name"]

        
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://googleadsapicalls.onrender.com/check_auth_status/{self.state}') as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("status") == "complete":
                        self.refresh_token = result.get("refresh_token")
                        if self.refresh_token:
                            CONNECTION_STRING = os.getenv("CONNECTION_STRING")
                            credentials_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "credentials", business_name)
                            
                            update_result = credentials_collection.update_one(
                                {"credentials.client_id": self.client_id},
                                {"$set": {"credentials.refresh_token": self.refresh_token}},
                                upsert=False
                            )
                            if update_result.modified_count > 0:
                                self.enable_next_button()
                                await interaction.followup.send("Authentication successful! Click 'Next' to view your campaigns.", view=self, ephemeral=True)
                            else:
                                await interaction.followup.send("Failed to update credentials with refresh token. No documents were modified.", ephemeral=True)
                        else:
                            await interaction.followup.send("Refresh token not found in the response. Please try authorizing again.", ephemeral=True)
                    else:
                        await interaction.followup.send("Authorization not yet complete. Please make sure you've completed the authorization process and try again.", ephemeral=True)
                else:
                    await interaction.followup.send(f"Error: Received status code {response.status} from authentication server.", ephemeral=True)

    @discord.ui.button(label="Reauthorize", style=discord.ButtonStyle.secondary)
    async def reauthorize(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"Please try authorizing again using this link: {self.auth_url}", ephemeral=True)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, disabled=True)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        self.credentials['web']['refresh_token'] = self.refresh_token
        request_data = {
            "customer_id": self.customer_id,
            "credentials": self.credentials
        }

        async with aiohttp.ClientSession() as session:
            async with session.post('https://googleadsapicalls.onrender.com/get_campaigns', json=request_data) as response:
                if response.status == 200:
                    campaigns = await response.json()
                    if campaigns:
                        campaign_list = "\n".join([f"- {campaign['name']} (ID: {campaign['id']})" for campaign in campaigns])
                        await interaction.followup.send(f"Here are your campaigns:\n{campaign_list}", ephemeral=True)
                    else:
                        await interaction.followup.send("You don't have any campaigns yet.", ephemeral=True)
                else:
                    error_details = await response.text()
                    await interaction.followup.send(f"Failed to retrieve campaigns. Error: {error_details}", ephemeral=True)

    def enable_next_button(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.label == "Next":
                item.disabled = False
                break

class CampaignCreationModal(discord.ui.Modal, title='Create New Campaign'):
    def __init__(self):
        super().__init__()
        self.campaign_name = discord.ui.TextInput(label="Campaign Name", style=discord.TextStyle.short, required=True)
        self.daily_budget = discord.ui.TextInput(label="Daily Budget (in dollars)", style=discord.TextStyle.short, required=True)
        self.start_date = discord.ui.TextInput(label="Start Date (YYYY-MM-DD)", style=discord.TextStyle.short, required=True)
        self.end_date = discord.ui.TextInput(label="End Date (YYYY-MM-DD)", style=discord.TextStyle.short, required=True)
        self.add_item(self.campaign_name)
        self.add_item(self.daily_budget)
        self.add_item(self.start_date)
        self.add_item(self.end_date)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            daily_budget = float(self.daily_budget.value)
            start_date = datetime.datetime.strptime(self.start_date.value, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(self.end_date.value, "%Y-%m-%d").date()
            
            campaign_data = {
                "campaign_name": self.campaign_name.value,
                "daily_budget": daily_budget,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "customer_id": interaction.client.customer_id,
                "credentials": interaction.client.credentials
            }

            async with aiohttp.ClientSession() as session:
                async with session.post('https://googleadsapicalls.onrender.com//create_campaign', json=campaign_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        await interaction.followup.send(f"Campaign created successfully! Campaign ID: {result['campaign_id']}", ephemeral=True)
                        CONNECTION_STRING = os.getenv("CONNECTION_STRING")
                        mappings_collection = connect_to_mongo_and_get_collection(CONNECTION_STRING, "mappings", "companies")
                        user_record = mappings_collection.find_one({"owner_ids": interaction.user.id})        
                        if user_record and "business_name" in user_record:
                            business_name = user_record["business_name"]

                        ad_variations = await helperfuncs.fetch_ad_variations(business_name)
                        if ad_variations and 'ad_variation' in ad_variations:
                            view = AdVariationView(
                                ad_variations['ad_variation'],
                                interaction.client.customer_id,
                                interaction.client.credentials,
                                self.campaign_name.value
                            )
                            embed = view.get_embed()
                            await interaction.followup.send(
                                "Please review and select the ad variations for this campaign:",
                                embed=embed,
                                view=view,
                                ephemeral=True
                            )
                        else:
                            await interaction.followup.send(
                                "Failed to fetch ad variations. Please try again later.",
                                ephemeral=True
                            )
                    else:
                        error_details = await response.text()
                        await interaction.followup.send(f"Failed to create campaign. Error: {error_details}", ephemeral=True)
        except ValueError as e:
            await interaction.followup.send(f"Invalid input: {str(e)}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

class AdVariationView(View):
    def __init__(self, ad_variations, customer_id, credentials, campaign_name, business_website):
        super().__init__()
        self.ad_variations = ad_variations
        self.customer_id = customer_id
        self.credentials = credentials
        self.campaign_name = campaign_name
        self.current_index = 0
        self.selected_ads = set()
        self.business_website = business_website

        self.add_item(Button(label="Previous", style=discord.ButtonStyle.gray, custom_id="previous"))
        self.add_item(Button(label="Next", style=discord.ButtonStyle.gray, custom_id="next"))
        self.add_item(Button(label="Select", style=discord.ButtonStyle.green, custom_id="select"))
        self.add_item(Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="edit"))
        self.add_item(Button(label="Finish", style=discord.ButtonStyle.blurple, custom_id="finish"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data["custom_id"] == "previous":
            self.current_index = max(0, self.current_index - 1)
        elif interaction.data["custom_id"] == "next":
            self.current_index = min(len(self.ad_variations) - 1, self.current_index + 1)
        elif interaction.data["custom_id"] == "select":
            if self.current_index in self.selected_ads:
                self.selected_ads.remove(self.current_index)
            else:
                self.selected_ads.add(self.current_index)
        elif interaction.data["custom_id"] == "edit":
            modal = AdVariationEditModal(self.ad_variations[self.current_index], self.current_index)
            await interaction.response.send_modal(modal)
            await modal.wait()
            if modal.result:
                index, updated_ad = modal.result
                self.ad_variations[index] = updated_ad
                self.selected_ads.add(index)
                await self.finish_selection(interaction)
            return True
        elif interaction.data["custom_id"] == "finish":
            await self.finish_selection(interaction)
            return True

        await self.update_message(interaction)
        return True
    
    async def open_edit_modal(self, interaction: discord.Interaction):
        current_ad = self.ad_variations[self.current_index]
        modal = AdVariationEditModal(current_ad, self.current_index)
        await interaction.response.send_modal(modal)

    async def on_modal_submit(self, interaction: discord.Interaction, index: int, updated_ad: dict):
        self.ad_variations[index] = updated_ad
        self.selected_ads.add(index)
        await interaction.response.send_message(f"Ad Variation {index + 1} updated and selected.", ephemeral=True)
        await self.finish_selection(interaction)


    async def update_message(self, interaction: discord.Interaction):
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def get_embed(self):
        ad = self.ad_variations[self.current_index]
        embed = discord.Embed(title=f"Ad Variation {self.current_index + 1}", color=discord.Color.blue())
        embed.add_field(name="Headlines", value="\n".join(ad["headlines"]), inline=False)
        embed.add_field(name="Descriptions", value="\n".join(ad["descriptions"]), inline=False)
        embed.add_field(name="Keywords", value=", ".join(ad["keywords"]), inline=False)
        embed.set_footer(text=f"Ad {self.current_index + 1} of {len(self.ad_variations)} | {'Selected' if self.current_index in self.selected_ads else 'Not Selected'}")
        return embed

    async def finish_selection(self, interaction: discord.Interaction):
        if not self.selected_ads:
            await interaction.followup.send("No ads selected. Please select at least one ad.", ephemeral=True)
            return

        selected_variations = [self.ad_variations[i] for i in self.selected_ads]
        view = ConfirmSelectedAdsView(selected_variations, self.customer_id, self.credentials, self.campaign_name, self.business_website)
        embeds = view.get_embeds()
        await interaction.followup.send("Here are your selected ads:", embeds=embeds, view=view, ephemeral=True)
        self.stop()

class AdVariationEditModal(discord.ui.Modal):
    def __init__(self, ad, index):
        super().__init__(title=f"Edit Ad Variation {index + 1}")
        self.ad = ad
        self.index = index
        self.result = None

        self.headlines = discord.ui.TextInput(
            label="Headlines (comma-separated)",
            style=discord.TextStyle.paragraph,
            default=", ".join(ad["headlines"]),
            required=True,
            max_length=1000
        )
        self.add_item(self.headlines)

        self.descriptions = discord.ui.TextInput(
            label="Descriptions (comma-separated)",
            style=discord.TextStyle.paragraph,
            default=", ".join(ad["descriptions"]),
            required=True,
            max_length=1000
        )
        self.add_item(self.descriptions)

        self.keywords = discord.ui.TextInput(
            label="Keywords (comma-separated)",
            style=discord.TextStyle.paragraph,
            default=", ".join(ad["keywords"]),
            required=True,
            max_length=1000
        )
        self.add_item(self.keywords)

    def get_warning_text(self, headlines, descriptions):
        warnings = []
        for i, headline in enumerate(headlines):
            if len(headline) > 30:
                warnings.append(f"Headline {i+1} exceeds limit by {len(headline) - 30} characters")
        for i, description in enumerate(descriptions):
            if len(description) > 90:
                warnings.append(f"Description {i+1} exceeds limit by {len(description) - 90} characters")
        return " | ".join(warnings) if warnings else "No warnings"

    async def on_submit(self, interaction: discord.Interaction):
        new_headlines = [h.strip() for h in self.headlines.value.split(",")]
        new_descriptions = [d.strip() for d in self.descriptions.value.split(",")]
        new_keywords = [k.strip() for k in self.keywords.value.split(",")]

        warning_text = self.get_warning_text(new_headlines, new_descriptions)
        if warning_text != "No warnings":
            await interaction.response.send_message(f"Cannot submit. {warning_text}. Please edit and try again.", ephemeral=True)
            return None, None

        updated_ad = {
            "headlines": new_headlines,
            "descriptions": new_descriptions,
            "keywords": new_keywords
        }
        
        self.result = (self.index, updated_ad)
        await interaction.response.defer(ephemeral=True)

class ConfirmSelectedAdsView(discord.ui.View):
    def __init__(self, selected_ads, customer_id, credentials, campaign_name, business_website):
        super().__init__()
        self.selected_ads = selected_ads
        self.customer_id = customer_id
        self.credentials = credentials
        self.campaign_name = campaign_name
        self.business_website = business_website

        self.add_item(discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green, custom_id="confirm"))
        self.add_item(discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green, custom_id="confirm"))
        self.add_item(discord.ui.Select(
            placeholder="Select an ad to delete",
            options=[discord.SelectOption(label=f"Ad {i+1}", value=str(i)) for i in range(len(selected_ads))],
            custom_id="delete"
        ))

    def get_embeds(self):
            embeds = []
            for i, ad in enumerate(self.selected_ads):
                embed = discord.Embed(title=f"Selected Ad {i+1}", color=discord.Color.blue())
                embed.add_field(name="Headlines", value=ad["headlines"], inline=False)
                embed.add_field(name="Descriptions", value=ad["descriptions"], inline=False)
                embed.add_field(name="Keywords", value=", ".join(ad["keywords"]), inline=False)
                embeds.append(embed)
            return embeds

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.data["custom_id"] == "confirm":
                await interaction.response.send_message("Ads confirmed and will be used for the campaign!", ephemeral=True)
                await self.create_ads(interaction)
                self.stop()
            elif interaction.data["custom_id"] == "delete":
                index = int(interaction.data["values"][0])
                del self.selected_ads[index]
                if not self.selected_ads:
                    await interaction.response.send_message("All ads deleted. Returning to ad selection.", ephemeral=True)
                    self.stop()
                else:
                    embeds = self.get_embeds()
                    await interaction.response.edit_message(content="Here are your updated selected ads:", embeds=embeds, view=self)
            return True

    async def create_ads(self, interaction: discord.Interaction):
        await interaction.followup.send("Creating ads, please wait...", ephemeral=True)
        success_count = 0
        for ad in self.selected_ads:
            success = await self.create_ad(ad)
            if success:
                success_count += 1
        await interaction.followup.send(f"{success_count} out of {len(self.selected_ads)} ads were created successfully!", ephemeral=True)

    async def create_ad(self, ad):
        cleaned_campaign_name = self.campaign_name.strip().lstrip('-').strip()
        ad_data = {
            "customer_id": self.customer_id,
            "business_website": self.business_website,
            "campaign_name": cleaned_campaign_name,
            "headlines": ad["headlines"],
            "descriptions": ad["descriptions"],
            "keywords": ad["keywords"],
            "credentials": self.credentials
        }
        async with aiohttp.ClientSession() as session:
            print('ad_data', ad_data)
            async with session.post('https://googleadsapicalls.onrender.com/create_ad', json=ad_data) as response:
                if response.status == 200:
                    return True
                else:
                    print(f"Failed to create ad: {await response.text()}")
                    return False