# cogs/rota.py
import discord
from discord.ext import commands
from discord import app_commands


# ID D’UN RÔLE TEST (tu mets ce que tu veux)
ROLE_TEST = 1421867268421320844   # ton rôle test déjà présent dans ton serveur


# ----------- BOUTON MINIMAL -----------
class TestButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Rôle Test", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(ROLE_TEST)
        member = interaction.user

        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message("Rôle test retiré.", ephemeral=True)
        else:
            await member.add_roles(role)
            await interaction.response.send_message("Rôle test ajouté.", ephemeral=True)


# ----------- VIEW MINIMALE -----------
class TestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TestButton())


# ----------- COG / COMMANDE -----------
class RotaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rota", description="Panel test minimal")
    async def rota(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Panel test chargé.",
            view=TestView(),
            ephemeral=False
        )


async def setup(bot):
    await bot.add_cog(RotaCog(bot))
