import discord
from discord.ext import commands
from discord import app_commands

ADMIN_ROLE_NAME = "ADMIN"
DEV_PS_ROLE_ID = 1542570443054260405


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

        # Autorisation
        is_admin = ADMIN_ROLE_NAME in [r.name for r in interaction.user.roles]
        is_dev_ps = DEV_PS_ROLE_ID in [r.id for r in interaction.user.roles]

        if not (is_admin or is_dev_ps):
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

        # Exactement comme dans ton code d'origine
        await interaction.response.send_message(embed=embed)

        # SEULE NOUVELLE LOGIQUE :
        # choisir le salon selon le serveur
        if interaction.guild.id == 1480943110929518605:
            paris_channel_id = 1480960334729842788

        elif interaction.guild.id == 1029095704129454211:
            paris_channel_id = 1510044180796407979

        else:
            return

        # Exactement comme dans ton code d'origine
        channel = self.bot.get_channel(paris_channel_id)

        if channel:
            await channel.send(embed=embed)
            await channel.send(f"Bonne chance {joueur.mention} 🍀")


async def setup(bot):
    await bot.add_cog(PariCog(bot))
