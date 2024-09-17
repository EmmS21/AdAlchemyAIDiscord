import re
from datetime import datetime, timezone
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

        message_sent = False
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and not message_sent:
                await channel.send(welcome_back_message)
                await channel.send(calendly_message)
                message_sent = True
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
        mappings_collection.insert_one(new_user_data)

        welcome_message = """
        Hello! I am AdAlchemyAI, a bot to help you get good leads for a cost-effective price for your business by automating the process of setting up, running, and optimizing your Google Ads. I only run ads after you manually approve the keywords I researched, the ad text ideas I generate, and the information I use to carry out my research.

        But for now, I would like to learn more about you and your business.
        """
        first_question = "What is the name of your business?"
        guild_onboarded_status[guild.id] = False

        message_sent = False
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages and not message_sent:
                await channel.send(welcome_message)
                await channel.send(first_question)
                message_sent = True
                break

        guild_states[guild.id] = "waiting_for_business_name"

async def handle_message(message, mappings_collection, guild_states):
    if message.author.bot:
        return

    guild_id = message.guild.id
    current_state = guild_states.get(guild_id)

    user_record = mappings_collection.find_one({"owner_ids": message.guild.owner.id})
    
    if not user_record:
        return
    
    async def process_business_name():
        business_name = message.content.lower()
        mappings_collection.update_one(
            {"_id": user_record["_id"]},
            {"$set": {"business_name": business_name}}
        )
        await message.channel.send(f"Please give me a link to your website {business_name}:")
        guild_states[guild_id] = "waiting_for_website"


    async def process_website():
        url_pattern = re.compile(r'^https?://(?:www\.)?[a-zA-Z0-9-]{1,63}\.[a-zA-Z]{2,63}(?:/\S*)?$')

        if re.match(url_pattern, message.content):
            website_link = message.content
            mappings_collection.update_one(
                {"_id": user_record["_id"]},
                {"$set": {"website_link": website_link}}
            )
            await message.channel.send("We are currently running in beta")
            await message.channel.send("Please confirm your interest in joining the AdAlchemyAI waiting list")
            guild_states[guild_id] = "waiting_for_consent"
        else:
            await message.channel.send("That doesn't appear to be a valid URL. Please enter a valid website URL (e.g., https://www.example.com):")

    if current_state == "waiting_for_business_name":
        await process_business_name()
    elif current_state == "waiting_for_website":
        await process_website()
