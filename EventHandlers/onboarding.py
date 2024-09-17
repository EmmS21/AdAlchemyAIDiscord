import re
from datetime import datetime, timezone

import discord
from MongoDBConnection.connectMongo import connect_to_mongo_and_get_collection
import os
import Helpers.helperClasses as helperClasses

async def handle_guild_join(guild, guild_onboarded_status, guild_states):
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
        if new_user_data["business_name"] is not None:
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

async def handle_message(message, guild_states):
    if isinstance(message, discord.WebhookMessage):
        guild_id = message.guild.id
        author_id = message.author.id
    elif message.author.bot and not message.webhook_id:
        return 
    else:
        guild_id = message.guild.id
        author_id = message.author.id
    
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
            view = helperClasses.ConfirmPricing(guild_id, business_name, website_link)
            await message.channel.send("Please confirm your interest in joining the AdAlchemyAI waiting list", view=view)
            guild_states[guild_id] = "waiting_for_consent"
        else:
            await message.channel.send("That doesn't appear to be a valid URL. Please enter a valid website URL (e.g., https://www.example.com):")