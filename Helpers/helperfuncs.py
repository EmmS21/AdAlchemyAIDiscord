import aiohttp
import discord

from Helpers.helperClasses import AdVariationView, CampaignCreationModal


def website_exists_in_db(db, website_link):
    if db is None:
        raise ValueError("Database connection is not established.")
    for collection_name in db.list_collection_names():
        collection = db[collection_name]
        if collection.find_one({"website": website_link}):
            return True
    return False

def get_latest_document(collection):
    """
    Retrieves the last inserted document from the given collection.

    Args:
    - collection: MongoDB collection object

    Returns:
    - dict: The last inserted document, or None if no documents exist
    """
    cursor = collection.find().sort('$natural', -1).limit(1)
    try:
        return next(cursor)
    except StopIteration:
        return None  
    
async def create_campaign_flow(interaction: discord.Interaction, customer_id: str, credentials: dict):
    # Store the credentials and customer_id for later use
    interaction.client.customer_id = customer_id
    interaction.client.credentials = credentials

    class CreateCampaignButton(discord.ui.View):
        @discord.ui.button(label="Create Campaign", style=discord.ButtonStyle.primary)
        async def button_callback(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            modal = CampaignCreationModal()
            await button_interaction.response.send_modal(modal)

    view = CreateCampaignButton()
    await interaction.followup.send("Click the button below to create a new campaign:", view=view, ephemeral=True)

async def fetch_ad_variations(business_name):
    url = 'https://emms21--ad-selector-agent-fetch-and-process.modal.run/'
    params = {'business_name': business_name}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as response:
            print('Response status:', response.status)
            if response.status == 200:
                return await response.json()
            else:
                print('Error response:', await response.text())
                return None

async def get_campaigns(interaction: discord.Interaction, customer_id: str, credentials: dict, business_name: str, business_website: str):
    request_data = {
        "customer_id": customer_id,
        "credentials": {
            "refresh_token": credentials.get("refresh_token"),
            "token_uri": credentials.get("token_uri", "https://oauth2.googleapis.com/token"),
            "client_id": credentials.get("client_id"),
            "client_secret": credentials.get("client_secret"),
            "developer_token": credentials.get("developer_token"),
            "scopes": credentials.get("scopes", ['https://www.googleapis.com/auth/adwords'])
        }
    }
    async with aiohttp.ClientSession() as session:
            async with session.post('https://googleadsapicalls.onrender.com/get_campaigns', json=request_data) as response:
                if response.status == 200:
                    campaigns_data = await response.json()
                    if campaigns_data:
                        all_campaigns = []
                        for account_id, account_data in campaigns_data.items():
                            account_name = account_data.get('Account Name', 'Unknown Account')
                            for campaign in account_data.get('Campaigns', []):
                                all_campaigns.append({
                                    'name': f"{account_name} - {campaign['Campaign Name']}",
                                    'id': campaign['Campaign ID'],
                                    'budget': campaign['Budget']
                                })
                        
                        if all_campaigns:
                            options = [
                                discord.SelectOption(
                                    label=f"{campaign['name']} (Budget: ${campaign['budget']:.2f})",
                                    value=str(campaign['id']),
                                    description=f"Campaign ID: {campaign['id']}"
                                ) for campaign in all_campaigns[:25] 
                            ]
                            select_menu = discord.ui.Select(
                                placeholder="Choose a campaign",
                                options=options
                            )
                            async def campaign_selected(interaction: discord.Interaction):
                                selected_campaign_id = select_menu.values[0]
                                selected_campaign = next((c for c in all_campaigns if str(c['id']) == selected_campaign_id), None)
                                if selected_campaign:
                                    await interaction.response.send_message(
                                        f"You selected: {selected_campaign['name']}\n"
                                        f"Campaign ID: {selected_campaign['id']}\n"
                                        f"Budget: ${selected_campaign['budget']:.2f}",
                                        ephemeral=True
                                    )
                                    ad_variations = await fetch_ad_variations(business_name)
                                    if ad_variations and 'ad_variation' in ad_variations:
                                        view = AdVariationView(
                                            ad_variations['ad_variation'],
                                            customer_id,
                                            credentials,
                                            selected_campaign['name'],
                                            business_website
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
                                    await interaction.response.send_message("Error: Campaign not found", ephemeral=True)

                            select_menu.callback = campaign_selected
                            view = discord.ui.View()
                            view.add_item(select_menu)

                            await interaction.followup.send("Please select a campaign to post your ad to:", view=view, ephemeral=True)
                        else:
                            await interaction.followup.send("No campaigns found in the accounts.", ephemeral=True)
                    else:
                        await interaction.followup.send("No campaign data returned from the server.", ephemeral=True)
                else:
                    error_details = await response.text()
                    await interaction.followup.send(f"Failed to retrieve campaigns. Error: {error_details}", ephemeral=True)