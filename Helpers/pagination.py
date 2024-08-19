import discord
from discord.ui import View, Button

class PaginationView(View):
    def __init__(self, pages):
        super().__init__(timeout=300)
        self.pages = pages
        self.current_page = 0

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content=self.pages[self.current_page], view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await self.update_message(interaction)
        else:
            await interaction.response.defer()

def create_paginated_embed(data: str, max_chars: int = 1900):
    pages = []
    current_page = ""
    
    for line in data.split('\n'):
        if len(current_page) + len(line) + 1 > max_chars:
            pages.append(current_page.strip())
            current_page = line + '\n'
        else:
            current_page += line + '\n'
    
    if current_page:
        pages.append(current_page.strip())
    
    return pages