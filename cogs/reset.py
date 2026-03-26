# cogs/leaderboard_reset.py

from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

LEADERBOARD_CHANNEL_ID = 1459091766098788445
ADMIN_ROLE_ID = 1280396795046006836
OWNER_ID = 1352575142668013588  # Ton ID

class LeaderboardReset(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="reset",
        description="Réinitialise les deux leaderboards (admin uniquement)."
    )
    async def reset(self, interaction: discord.Interaction):
        # Vérification des permissions
        if not any(r.id == ADMIN_ROLE_ID for r in getattr(interaction.user, "roles", [])) \
           and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(
                "❌ Tu n'as pas la permission.", ephemeral=True
            )

        # Récupération des cogs leaderboard
        leaderboard = self.bot.get_cog("Leaderboard")
        triggers = self.bot.get_cog("LeaderboardTriggers")

        if not leaderboard and not triggers:
            return await interaction.response.send_message(
                "❌ Les leaderboards ne sont pas chargés.", ephemeral=True
            )

        channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ Impossible d'accéder au channel leaderboard.", ephemeral=True
            )

        # Supprime les messages existants
        async for msg in channel.history(limit=50):
            if msg.author.id != self.bot.user.id or not msg.embeds:
                continue
            if msg.embeds[0].title in [
                "📊 Leaderboard Défense Percepteurs",
                "🚨 Leaderboard Déclencheurs d’Alertes"
            ]:
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass

        # Crée un nouveau message vide pour chaque leaderboard
        if leaderboard:
            await channel.send(embed=leaderboard.build_embed())
        if triggers:
            await channel.send(embed=triggers.build_embed())

        await interaction.response.send_message(
            "✅ Leaderboards réinitialisés.", ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardReset(bot))