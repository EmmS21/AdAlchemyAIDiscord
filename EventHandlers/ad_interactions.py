import os
import json
import aiohttp
import logging
from discord import Interaction
import discord
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
import Helpers.helperfuncs as helperfuncs
import Helpers.helperClasses as helperClasses

logger = logging.getLogger(__name__)

async def handle_keywords(interaction: Interaction, check_onboarded_status):
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

        latest_document = helperfuncs.get_latest_document(business_collection)
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

        view = helperClasses.KeywordPaginationView(selected_keywords, new_keywords, business_collection, title, last_update)
        embed = view.get_embed()
        await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        logger.error(f"Error in keywords command: {str(e)}", exc_info=True)
        await interaction.followup.send("An error occurred while processing your request. Please try again later or contact support if the issue persists.", ephemeral=True)

async def handle_adtext(interaction: Interaction, check_onboarded_status):
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
                latest_document = helperfuncs.get_latest_document(business_collection)
                
                if latest_document and 'ad_variations' in latest_document:
                    ad_variations = latest_document['ad_variations']
                    finalized_ad_texts = latest_document.get('finalized_ad_text', [])
                    last_update = latest_document.get('last_update', 'N/A')
                    
                    view = helperClasses.AdTextView(ad_variations, finalized_ad_texts, business_collection, last_update)
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

async def handle_upload_credentials(interaction: Interaction, credentials_file: discord.Attachment, customer_id: str, check_onboarded_status):
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

async def handle_create_ad(interaction: Interaction, check_onboarded_status):
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

            async def select_callback(interaction: Interaction):
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
                                        await helperfuncs.get_campaigns(interaction, customer_id, complete_credentials, business_name, business_website)
                                    else:
                                        await helperfuncs.create_campaign_flow(interaction, customer_id, complete_credentials)
                                elif "auth_url" in result and "state" in result:
                                    auth_url = result["auth_url"]
                                    state = result["state"]
                                    view = helperClasses.AuthCompletedView(auth_url, state, credentials['client_id'], customer_id, web_credentials)
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