import discord
from discord.ext import commands
from discord import app_commands

ADMIN_ROLE_NAME = "ADMIN"

# ID SERVEUR : ID SALON PARIS
PARIS_CHANNELS = {
    1480943110929518605: 1480960334729842788,  # Serveur 1
    1029095704129454211: 1510044180796407979,  # Serveur 2
}

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

        # La commande doit être utilisée dans un serveur
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Cette commande doit être utilisée sur un serveur.",
                ephemeral=True
            )

        # Vérification des rôles autorisés
        is_admin = any(
            role.name == ADMIN_ROLE_NAME
            for role in interaction.user.roles
        )

        is_dev_ps = any(
            role.id == DEV_PS_ROLE_ID
            for role in interaction.user.roles
        )

        if not (is_admin or is_dev_ps):
            return await interaction.response.send_message(
                "❌ Tu n’es pas autorisé.",
                ephemeral=True
            )

        # Récupération du salon correspondant au serveur
        paris_channel_id = PARIS_CHANNELS.get(interaction.guild.id)

        if paris_channel_id is None:
            return await interaction.response.send_message(
                "❌ Le système de paris n'est pas configuré sur ce serveur.",
                ephemeral=True
            )

        # Lecture de la mise
        try:
            mise_val = parse_mise(mise)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Mise invalide.",
                ephemeral=True
            )

        # Calculs
        cote_kamazone = round(cote_winamax * 0.8, 2)
        gain = round(mise_val * cote_kamazone, 2)

        # Embed
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

        # Confirmation à la personne qui crée le pari
        await interaction.response.send_message(
            "✅ Pari créé.",
            ephemeral=True
        )

        # Salon du serveur concerné
        channel = interaction.guild.get_channel(paris_channel_id)

        if channel is None:
            return await interaction.followup.send(
                "❌ Le salon de paris configuré est introuvable.",
                ephemeral=True
            )

        # Envoi du pari
        await channel.send(embed=embed)
        await channel.send(
            f"Bonne chance {joueur.mention} 🍀"
        )


async def setup(bot):
    await bot.add_cog(PariCog(bot))
