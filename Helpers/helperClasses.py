import discord
from discord import ButtonStyle, Embed, TextStyle
from discord.ui import Button, View, TextInput, Modal
from collections import defaultdict
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
from Helpers.helperfuncs import get_latest_document
import os
from pymongo.errors import WriteError

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
        latest_document = get_latest_document(self.collection)
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
        latest_document = get_latest_document(self.collection)
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
        
        # Convert keywords to a list if it's a dictionary
        if isinstance(keywords, dict):
            keywords_list = list(keywords.items())
        else:
            keywords_list = keywords
        
        current_keywords = keywords_list[start:end]

        title = "Previously Selected Keywords" if self.current_keyword_type == "selected" else "New Keywords"
        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.description = "Use the menu above to switch between keyword categories."

        for keyword in current_keywords:
            if isinstance(keyword, tuple):  # If keywords is a dict
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
                    
                    if isinstance(keyword, tuple):  # If keywords was originally a dict
                        keyword_text = keyword[0]
                        keyword_data = keyword[1]
                    elif isinstance(keyword, dict) and 'text' in keyword:
                        keyword_text = keyword['text']
                        keyword_data = keyword
                    elif isinstance(keyword, str):
                        keyword_text = keyword
                        keyword_data = {'text': keyword}
                    else:
                        return False  # Invalid keyword format
                    
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
    def __init__(self, ad_variations, finalized_ad_texts, collection):
        super().__init__()
        self.headlines = [ad['headline'] for ad in ad_variations]
        self.descriptions = [ad['description'] for ad in ad_variations]
        self.finalized_ad_texts = finalized_ad_texts
        self.collection = collection
        self.current_page = 0
        self.total_ads = min(len(self.headlines), len(self.descriptions))
        
        self.previous_button = Button(style=ButtonStyle.gray, disabled=True)
        self.previous_button.label = "Previous"
        self.next_button = Button(style=ButtonStyle.gray)
        self.next_button.label = "Next"
        self.edit_button = Button(style=ButtonStyle.primary)
        self.edit_button.label = "Edit"
        
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
        finalized_ad = next((fad for fad in self.finalized_ad_texts if fad['index'] == self.current_page), None)
        
        if finalized_ad:
            title = f"Ad Variation {self.current_page + 1} (Finalized)"
            headline = finalized_ad['headline']
            description = finalized_ad['description']
        else:
            title = f"Ad Variation {self.current_page + 1}"
            headline = self.headlines[self.current_page]
            description = self.descriptions[self.current_page]

        embed = Embed(title=title, color=discord.Color.blue())
        embed.add_field(name="Headline", value=headline, inline=False)
        embed.add_field(name="Description", value=description, inline=False)
        embed.set_footer(text=f"Ad {self.current_page + 1} of {self.total_ads}")
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
            label=f'Headline {"(Finalized)" if is_finalized else ""} (recommended max 30 characters)',
            style=TextStyle.short,
            default=headline,
            required=True,
            max_length=200  # Allow longer input, but warn about it
        )

        self.description = TextInput(
            label=f'Description {"(Finalized)" if is_finalized else ""} (recommended max 90 characters)',
            style=TextStyle.paragraph,
            default=description,
            required=True,
            max_length=200  # Allow longer input, but warn about it
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

            latest_document = get_latest_document(self.collection)

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