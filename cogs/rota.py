# cogs/rota.py
import discord
from discord.ext import commands
from discord import app_commands

# -------------------------------------------------
# CONFIG — À REMPLIR AVEC TES IDS DE RÔLES
# -------------------------------------------------

ROLES = {
    "Klime": 1440248122365444150,
    "Sylargh": 1440248027636830259,
    "Missiz": 1440248234353360967,
    "Nileza": 1440248191605014619,

    "Aerdala": 1440248330860105810,
    "Terrdala": 1440248148726517931,
    "Feudala": 1440248267332911145,
    "Plantala": 1440248294575177862,

    "Grobe": 1440248376657580042,
    "Frigost 2": 1440248458920460358,
    "DJ oeuf": 1440248402783895572,
    "Donjon": 1440248434891292713,

    "Autre": 1440248484853841972,
}

# -------------------------------------------------
# EMOJIS PANEL
# -------------------------------------------------

EMOJIS = {
    "Klime": "🧥",
    "Sylargh": "⚙️",
    "Missiz": "❄️",
    "Nileza": "🧊",

    "Aerdala": "🌪️",
    "Terrdala": "🪨",
    "Feudala": "🔥",
    "Plantala": "🌿",

    "Grobe": "👻",
    "Frigost 2": "🧊",
    "DJ oeuf": "🥚",
    "Donjon": "🏰",

    "Autre": "📌",
    "Aucun": "❌",
}

# -------------------------------------------------
# VIEW DES BOUTONS
# -------------------------------------------------

class RotaButton(discord.ui.Button):
    def __init__(self, label: str, role_id: int | None, style: discord.ButtonStyle, row: int):
        super().__init__(label=label, emoji=EMOJIS[label], style=style, row=row)
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user

        # Bouton "Aucun" → retirer tous les rôles du panel
        if self.label == "Aucun":
            removed_any = False
            for r_id in ROLES.values():
                role = guild.get_role(r_id)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    removed_any = True

            if removed_any:
                await interaction.response.send_message(
                    "Tous tes rôles rota ont été retirés.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Tu n'avais aucun rôle rota.",
                    ephemeral=True
                )
            return

        # Sinon → toggle du rôle classique
        role = guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("Rôle introuvable.", ephemeral=True)
            return

        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(f"Rôle retiré : **{self.label}**", ephemeral=True)
        else:
            await member.add_roles(role)
            await interaction.response.send_message(f"Rôle ajouté : **{self.label}**", ephemeral=True)


class RotaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        # Ligne 1 (vert)
        for name in ["Klime", "Sylargh", "Missiz", "Nileza"]:
            self.add_item(RotaButton(name, ROLES[name], discord.ButtonStyle.success, row=0))

        # Ligne 2 (vert)
        for name in ["Aerdala", "Terrdala", "Feudala", "Plantala"]:
            self.add_item(RotaButton(name, ROLES[name], discord.ButtonStyle.success, row=1))

        # Ligne 3 (vert)
        for name in ["Grobe", "Frigost 2", "DJ oeuf", "Donjon"]:
            self.add_item(RotaButton(name, ROLES[name], discord.ButtonStyle.success, row=2))

        # Ligne 4 (bleu puis rouge)
        self.add_item(RotaButton("Autre", ROLES["Autre"], discord.ButtonStyle.primary, row=3))
        self.add_item(RotaButton("Aucun", None, discord.ButtonStyle.danger, row=3))


# -------------------------------------------------
# COG
# -------------------------------------------------

class RotaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rota", description="Affiche le panel de sélection des rôles rota.")
    async def rota(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🐴 Rotation percepteur",
            description=(
                "✨ **Clique sur un ou plusieurs boutons** pour choisir les zones où tu veux être ping.\n"
                "🔄 Clique à nouveau pour **retirer le rôle**.\n"
                "❌ Le bouton **Aucun** retire **tous** tes rôles de ping rota.\n\n"
                "📣 Ping le rôle concerné pour signaler que tu vas lever un percepteur pour une rota ! 🛡️"
            ),
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(embed=embed, view=RotaView())

async def setup(bot):
    await bot.add_cog(RotaCog(bot))
