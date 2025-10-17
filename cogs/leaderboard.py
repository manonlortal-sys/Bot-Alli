import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
from zoneinfo import ZoneInfo

from storage import (
    get_guild_config,
    get_teams,
    get_leaderboard_post,
    set_leaderboard_post,
    get_participants_user_ids,
    agg_totals_by_team,
    clear_baseline,
)

# ============================================================
# ============= LEADERBOARD COG (PAR GUILDE) =================
# ============================================================

async def build_guild_embed(bot, guild, team):
    """Construit l'embed d'une guilde avec toutes les stats."""
    w, l, inc, att = agg_totals_by_team(guild.id, team["team_id"])
    defenders = []

    # Récupération des défenseurs (tous les joueurs de la guilde ayant participé à au moins une défense)
    channel = bot.get_channel(get_guild_config(guild.id)["alert_channel_id"])
    if channel:
        async for m in channel.history(limit=500):
            if not m.embeds:
                continue
            emb = m.embeds[0]
            if not emb.title or not emb.title.startswith("🛡️ Alerte Attaque"):
                continue
            if hasattr(m, "team") and m.team == team["team_id"]:
                user_ids = get_participants_user_ids(m.id)
                for uid in user_ids:
                    if uid not in defenders:
                        defenders.append(uid)

    # Construire la liste de noms des défenseurs
    defenders_text = ""
    for uid in defenders[:30]:  # Limite pour éviter un embed trop long
        user = guild.get_member(uid)
        if user:
            defenders_text += f"• {user.mention}\n"

    emb = discord.Embed(
        title=f"🏰 {team['name']} — Leaderboard",
        color=discord.Color.gold()
    )
    emb.add_field(name="⚔️ Défenses totales", value=str(att), inline=True)
    emb.add_field(name="🏆 Victoires", value=str(w), inline=True)
    emb.add_field(name="💀 Défaites", value=str(l), inline=True)
    emb.add_field(name="😡 Défenses incomplètes", value=str(inc), inline=True)
    emb.add_field(name="🧙 Défenseurs", value=defenders_text or "*Aucun défenseur enregistré*", inline=False)

    emb.set_footer(text="Remis à zéro chaque lundi à 00h00 (heure de Paris)")
    return emb


async def update_leaderboards(bot, guild):
    """Met à jour tous les leaderboards de guildes et celui des pingeurs."""
    cfg = get_guild_config(guild.id)
    if not cfg:
        return

    lb_channel = bot.get_channel(cfg["leaderboard_channel_id"])
    if not lb_channel:
        return

    teams = get_teams(guild.id)
    for team in teams:
        if team["name"].lower() == "prisme":
            continue

        channel_id, message_id = get_leaderboard_post(guild.id, f"guild_{team['team_id']}")
        emb = await build_guild_embed(bot, guild, team)

        try:
            if message_id:
                msg = await lb_channel.fetch_message(message_id)
                await msg.edit(embed=emb)
            else:
                msg = await lb_channel.send(embed=emb)
                set_leaderboard_post(guild.id, lb_channel.id, msg.id, f"guild_{team['team_id']}")
        except Exception:
            try:
                msg = await lb_channel.send(embed=emb)
                set_leaderboard_post(guild.id, lb_channel.id, msg.id, f"guild_{team['team_id']}")
            except Exception:
                continue


class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ============================================================
    # ======= COMMANDE MANUELLE POUR RESET LEADERBOARDS ==========
    # ============================================================

    @app_commands.command(name="reset-leaderboards", description="Remet tous les leaderboards (sauf pingeur) à zéro et met à jour les messages.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboards(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        # Supprime les stats en base sauf pingeur
        clear_baseline(guild.id)

        # Met à jour les leaderboards immédiatement
        await update_leaderboards(self.bot, guild)

        # Enregistre un snapshot vide
        try:
            import cogs.snapshots as snaps
            payload = await snaps.SnapshotsCog._gather_snapshot_payload(snaps.SnapshotsCog(self.bot), guild)
            await snaps.SnapshotsCog._post_snapshot_file(snaps.SnapshotsCog(self.bot), guild, payload)
        except Exception:
            pass

        await interaction.followup.send("✅ Tous les leaderboards ont été remis à zéro (sauf Pingeur).", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
