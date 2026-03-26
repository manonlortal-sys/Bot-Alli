# cogs/reset.py
from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands
from cogs.leaderboard import LEADERBOARD_CHANNEL_ID, Leaderboard
from cogs.leaderboard_triggers import LeaderboardTriggers

ADMIN_ROLE_ID = 1280396795046006836
OWNER_ID = 1352575142668013588  # Ton ID

class ResetCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="reset",
        description="Réinitialise les deux leaderboards (admin uniquement)."
    )
    async def reset(self, interaction: discord.Interaction):
        # Vérification permissions
        if not any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles) and interaction.user.id != OWNER_ID:
            return await interaction.response.send_message(
                "❌ Tu n'as pas la permission.", ephemeral=True
            )

        # Récupère les cogs
        leaderboard = self.bot.get_cog("Leaderboard")
        triggers = self.bot.get_cog("LeaderboardTriggers")
        cogs = [leaderboard, triggers]

        channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ Impossible d'accéder au channel des leaderboards.", ephemeral=True
            )

        # Supprime les anciens messages
        async for msg in channel.history(limit=50):
            if msg.author.id != self.bot.user.id or not msg.embeds:
                continue
            if msg.embeds[0].title in ["📊 Leaderboard Défense Percepteurs",
                                       "🚨 Leaderboard Déclencheurs d’Alertes"]:
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass

        # Crée de nouveaux messages vides
        for cog in cogs:
            if cog:
                embed = cog.build_embed()
                await channel.send(embed=embed)

        await interaction.response.send_message(
            "✅ Leaderboards réinitialisés.", ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(ResetCog(bot))