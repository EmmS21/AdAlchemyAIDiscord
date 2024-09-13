import os

import discord
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
import Helpers.helperfuncs as helperfuncs
import Helpers.helperClasses as helperClasses
from discord import Embed

async def handle_business(interaction, check_onboarded_status):
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
                latest_document = helperfuncs.get_latest_document(business_collection)
                
                if latest_document and 'business' in latest_document:
                    business_data = latest_document['business']
                    
                    if not business_data:
                        await interaction.response.send_message("No business information found in the latest document.")
                        return
                    
                    view = helperClasses.BusinessView(business_data)
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

async def handle_research_paths(interaction, check_onboarded_status):
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
                latest_document = helperfuncs.get_latest_document(business_collection)
                
                if latest_document and 'list_of_paths_taken' in latest_document:
                    paths = latest_document['list_of_paths_taken']
                    
                    if not paths:
                        await interaction.response.send_message("No research paths found for your business in the latest document. Use the 'Add Path' button to add one.")
                        return
                    
                    view = helperClasses.ResearchPathsView(paths, business_name)
                    embed = view.get_embed()
                    await interaction.response.send_message(embed=embed, view=view)
                else:
                    view = helperClasses.ResearchPathsView([], business_name)
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

async def handle_user_personas(interaction, check_onboarded_status):
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
                latest_document = helperfuncs.get_latest_document(business_collection)
                
                if latest_document and 'user_personas' in latest_document:
                    personas = latest_document['user_personas']
                    if isinstance(personas, str):
                        personas = [personas] 
                    
                    view = helperClasses.UserPersonaView(personas, business_name)
                    embed = view.get_embed()
                    await interaction.response.send_message(embed=embed, view=view)
                else:
                    view = helperClasses.UserPersonaView([], business_name)
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