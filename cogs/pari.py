import discord
from discord.ext import commands
from discord import app_commands

PARIS_CHANNEL_ID_SERVEUR_1 = 1480960334729842788
PARIS_CHANNEL_ID_SERVEUR_2 = 1510044180796407979

SERVEUR_1_ID = 1480943110929518605
SERVEUR_2_ID = 1029095704129454211

DEV_PS_ROLE_ID = 1542570443054260405

ADMIN_ROLE_NAME = "ADMIN"


def format_kamas(amount):
    if amount >= 1_000_000_000:
        return f"{round(amount / 1_000_000_000, 2)}B"
    if amount >= 1_000_000:
        return f"{round(amount / 1_000_000, 2)}M"
    if amount >= 1_000:
        return f"{round(amount / 1_000, 2)}K"
    return str(round(amount, 2))


def parse_mise(mise_str):
    s = mise_str.replace(" ", "").lower()
    if s.endswith("m"):
        return float(s[:-1]) * 1_000_000
    if s.endswith("k"):
        return float(s[:-1]) * 1_000
    return float(s)


class PariCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="pari", description="Créer un pari sportif")
    async def pari(
        self,
        interaction: discord.Interaction,
        joueur: discord.Member,
        mise: str,
        cote_winamax: float
    ):

        # Autorisation d'origine + DEV PS
        roles_names = [r.name for r in interaction.user.roles]
        roles_ids = [r.id for r in interaction.user.roles]

        if (
            ADMIN_ROLE_NAME not in roles_names
            and DEV_PS_ROLE_ID not in roles_ids
        ):
            return await interaction.response.send_message(
                "❌ Tu n’es pas autorisé.",
                ephemeral=True
            )

        try:
            mise_val = parse_mise(mise)
        except:
            return await interaction.response.send_message(
                "❌ Mise invalide.",
                ephemeral=True
            )

        cote_kamazone = round(cote_winamax * 0.8, 2)
        gain = round(mise_val * cote_kamazone, 2)

        embed = discord.Embed(
            title="🎰 Pari Sportif",
            color=0xFFD700
        )

        embed.add_field(
            name="\u200b",
            value=f"""```
🎮 Joueur        │ {joueur.display_name}
💰 Mise          │ {format_kamas(mise_val)}
🎲 Winamax       │ {cote_winamax}
⚡ Kamazon       │ {cote_kamazone}
🏆 Gain          │ {format_kamas(gain)}
```""",
            inline=False
        )

        # IDENTIQUE À TON CODE ORIGINAL
        await interaction.response.send_message(embed=embed)

        # Seul ajout : choix de l'ID selon le serveur
        if interaction.guild.id == SERVEUR_1_ID:
            channel = self.bot.get_channel(PARIS_CHANNEL_ID_SERVEUR_1)

        elif interaction.guild.id == SERVEUR_2_ID:
            channel = self.bot.get_channel(PARIS_CHANNEL_ID_SERVEUR_2)

        else:
            channel = None

        # IDENTIQUE À TON CODE ORIGINAL
        if channel:
            await channel.send(embed=embed)
            await channel.send(f"Bonne chance {joueur.mention} 🍀")


async def setup(bot):
    await bot.add_cog(PariCog(bot))
