# cogs/reset.py

from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

LEADERBOARD_CHANNEL_ID = 1459091766098788445
ADMIN_ROLE_ID = 1280396795046006836  # rôle admin
ALLOWED_USER_ID = 1352575142668013588  # ton ID

class ResetCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="reset",
        description="Réinitialise les deux leaderboards (admin uniquement)."
    )
    async def reset(self, interaction: discord.Interaction):
        # Vérification permissions
        has_admin_role = any(r.id == ADMIN_ROLE_ID for r in getattr(interaction.user, "roles", []))
        if not has_admin_role and interaction.user.id != ALLOWED_USER_ID:
            return await interaction.response.send_message(
                "❌ Tu n'as pas la permission.", ephemeral=True
            )

        # Récupération des cogs leaderboard
        leaderboard_cog = self.bot.get_cog("Leaderboard")
        triggers_cog = self.bot.get_cog("LeaderboardTriggers")

        if not leaderboard_cog and not triggers_cog:
            return await interaction.response.send_message(
                "❌ Les cogs leaderboard ne sont pas chargés.", ephemeral=True
            )

        channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ Impossible d'accéder au salon des leaderboards.", ephemeral=True
            )

        # Supprime les messages existants
        async for msg in channel.history(limit=50):
            if msg.author.id != self.bot.user.id or not msg.embeds:
                continue
            title = msg.embeds[0].title
            if title in ["📊 Leaderboard Défense Percepteurs", "🚨 Leaderboard Déclencheurs d’Alertes"]:
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass

        # Recréation d'un message vierge pour chaque leaderboard
        for cog in [leaderboard_cog, triggers_cog]:
            if cog:
                await channel.send(embed=cog.build_embed())

        await interaction.response.send_message(
            "✅ Leaderboards réinitialisés.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ResetCog(bot))