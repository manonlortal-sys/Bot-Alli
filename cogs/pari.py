import discord
from discord.ext import commands
from discord import app_commands

ADMIN_ROLE_NAME = "ADMIN"

# ID SERVEUR : ID SALON PARIS
PARIS_CHANNELS = {
    1480943110929518605: 1480960334729842788,  # Serveur 1
    1029095704129454211: 1510044180796407979,  # Serveur 2
}


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

    @app_commands.command(
        name="pari",
        description="Créer un pari sportif"
    )
    async def pari(
        self,
        interaction: discord.Interaction,
        joueur: discord.Member,
        mise: str,
        cote_winamax: float
    ):

        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Cette commande doit être utilisée sur un serveur.",
                ephemeral=True
            )

        if ADMIN_ROLE_NAME not in [r.name for r in interaction.user.roles]:
            return await interaction.response.send_message(
                "❌ Tu n’es pas autorisé.",
                ephemeral=True
            )

        paris_channel_id = PARIS_CHANNELS.get(interaction.guild.id)

        if paris_channel_id is None:
            return await interaction.response.send_message(
                "❌ Le système de paris n'est pas configuré sur ce serveur.",
                ephemeral=True
            )

        try:
            mise_val = parse_mise(mise)
        except ValueError:
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

        await interaction.response.send_message(
            "✅ Pari créé.",
            ephemeral=True
        )

        channel = interaction.guild.get_channel(paris_channel_id)

        if channel is None:
            return await interaction.followup.send(
                "❌ Le salon de paris configuré est introuvable.",
                ephemeral=True
            )

        await channel.send(embed=embed)
        await channel.send(
            f"Bonne chance {joueur.mention} 🍀"
        )


async def setup(bot):
    await bot.add_cog(PariCog(bot))
