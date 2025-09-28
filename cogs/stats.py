# cogs/stats.py
from typing import Optional, List, Tuple
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
from discord import app_commands

from storage import (
    get_player_stats,
    get_player_recent_defenses,
    get_player_hourly_counts,
)

EMOJI_WIN = "🏆"
EMOJI_LOSS = "❌"
# Buckets: Matin (6–10), Journée (10–18), Soir (18–00), Nuit (00–6)
BUCKET_LABELS = ["🌅 Matin", "🌞 Journée", "🌙 Soir", "🌌 Nuit"]

class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="stats", description="Voir les stats d’un joueur")
    @app_commands.describe(member="Membre à inspecter (optionnel)")
    async def stats(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Commande à utiliser sur un serveur.", ephemeral=True)
            return

        target = member or interaction.user

        # Lecture DB (avec garde-fou)
        try:
            defenses, pings, wins, losses = get_player_stats(guild.id, target.id)
            recent = get_player_recent_defenses(guild.id, target.id, limit=3)  # [(ts, outcome)]
            h_counts = get_player_hourly_counts(guild.id, target.id)          # (m,a,s,n)
        except Exception:
            await interaction.response.send_message("⚠️ Impossible de récupérer les stats (DB).", ephemeral=True)
            return

        ratio = f"{(wins/(wins+losses)*100):.1f}%" if (wins + losses) else "0%"

        # Analyse horaires: bucket max
        if any(h_counts):
            max_idx = max(range(4), key=lambda i: h_counts[i])
            active_label = BUCKET_LABELS[max_idx]
        else:
            active_label = "—"

        # Formater les 3 dernières défenses
        lines_recent: List[str] = []
        for ts, outcome in recent:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(ZoneInfo("Europe/Paris"))
            date_str = dt.strftime("%d/%m/%Y")
            time_str = dt.strftime("%H:%M")
            if outcome == "win":
                res = f"{EMOJI_WIN} Victoire"
            elif outcome == "loss":
                res = f"{EMOJI_LOSS} Défaite"
            else:
                res = "⏳ En cours"
            lines_recent.append(f"• {date_str} à {time_str} — {res}")

        recent_block = "\n".join(lines_recent) if lines_recent else "_Aucune défense trouvée_"

        # Embed
        embed = discord.Embed(title=f"📊 Stats de {target.display_name}", color=discord.Color.blurple())
        embed.add_field(name="🛡️ Défenses prises", value=str(defenses), inline=True)
        embed.add_field(name="⚡ Pings envoyés", value=str(pings), inline=True)
        embed.add_field(name="🏆 Victoires", value=str(wins), inline=True)
        embed.add_field(name="❌ Défaites", value=str(losses), inline=True)
        embed.add_field(name="📊 Ratio victoire", value=ratio, inline=False)

        embed.add_field(name="🕒 Analyse des heures d’activité", value=f"Joueur surtout actif : {active_label}", inline=False)
        embed.add_field(name="🧾 3 dernières défenses prises", value=recent_block, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
