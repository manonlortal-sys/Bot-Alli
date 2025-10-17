import discord
from discord.ext import commands
from discord import app_commands
from zoneinfo import ZoneInfo

from storage import (
    get_guild_config,
    get_teams,
    get_leaderboard_post,
    set_leaderboard_post,
    get_participants_user_ids,
    agg_totals_by_team,
    get_message_team,
    get_leaderboard_totals,
    reset_all_leaderboards,   # <-- conserve "pingeur" via exclude
)

# ============================================================
# ============= LEADERBOARD COG (PAR GUILDE) =================
# ============================================================

async def build_guild_embed(bot: commands.Bot, guild: discord.Guild, team: dict) -> discord.Embed:
    """Construit l'embed d'une guilde avec stats + liste des défenseurs (≥1 def)."""
    tid = int(team["team_id"])
    w, l, inc, att = agg_totals_by_team(guild.id, tid)

    # Récupération des défenseurs : on scanne le canal d'alertes et on récupère
    # les participants des messages taggés avec la même team dans la DB.
    defenders = []
    cfg = get_guild_config(guild.id) or {}
    alerts_ch = bot.get_channel(cfg.get("alert_channel_id"))
    if isinstance(alerts_ch, discord.TextChannel):
        async for m in alerts_ch.history(limit=500):
            if not m.embeds:
                continue
            title = (m.embeds[0].title or "")
            if not title.startswith("🛡️ Alerte Attaque"):
                continue
            # Lier le message Discord à la team via la DB (pas d'attribut .team côté Discord)
            if get_message_team(m.id) != tid:
                continue
            for uid in get_participants_user_ids(m.id):
                if uid not in defenders:
                    defenders.append(uid)

    # Construire la liste (limite raisonnable pour l'embed)
    lines = []
    for uid in defenders[:30]:
        member = guild.get_member(uid)
        if member:
            lines.append(f"• {member.mention}")
    defenders_text = "\n".join(lines) if lines else "*Aucun défenseur enregistré*"

    emb = discord.Embed(
        title=f"🏰 {team['name']} — Leaderboard hebdomadaire",
        color=discord.Color.gold()
    )
    emb.add_field(name="🗡️ Attaques", value=str(att), inline=True)
    emb.add_field(name="🏆 Victoires", value=str(w), inline=True)
    emb.add_field(name="❌ Défaites", value=str(l), inline=True)
    emb.add_field(name="😡 Incomplètes", value=str(inc), inline=True)
    emb.add_field(name="👥 Défenseurs", value=defenders_text, inline=False)
    emb.set_footer(text="Remis à zéro chaque lundi à 00h00 (Europe/Paris)")
    return emb


async def update_leaderboards(bot: commands.Bot, guild: discord.Guild):
    """Met à jour le leaderboard Pingeurs + un embed par guilde (Prisme exclu)."""
    cfg = get_guild_config(guild.id)
    if not cfg:
        return
    ch = bot.get_channel(cfg["leaderboard_channel_id"])
    if not isinstance(ch, discord.TextChannel):
        return

    # =========================
    # 🛎️ Leaderboard PINGEURS
    # =========================
    post = get_leaderboard_post(guild.id, "pingeur")
    if post:
        _, ping_msg_id = post
        msg_ping = None
        try:
            msg_ping = await ch.fetch_message(ping_msg_id)
        except discord.NotFound:
            pass
    else:
        msg_ping = None

    # Build embed pingeurs
    top_ping = get_leaderboard_totals(guild.id, "pingeur", limit=20)
    ping_lines = []
    for i, (uid, cnt) in enumerate(top_ping):
        if i == 0:
            ping_lines.append(f"🥇 <@{uid}> — {cnt} pings")
        elif i == 1:
            ping_lines.append(f"🥈 <@{uid}> — {cnt} pings")
        elif i == 2:
            ping_lines.append(f"🥉 <@{uid}> — {cnt} pings")
        else:
            ping_lines.append(f"• <@{uid}> — {cnt} pings")
    ping_text = "\n".join(ping_lines) if ping_lines else "_Aucun pingeur encore_"
    ping_embed = discord.Embed(title="🛎️ Leaderboard Pingeurs", color=discord.Color.gold())
    ping_embed.add_field(name="**Top Pingeurs**", value=ping_text, inline=False)

    if msg_ping:
        await msg_ping.edit(embed=ping_embed)
    else:
        sent = await ch.send(embed=ping_embed)
        set_leaderboard_post(guild.id, ch.id, sent.id, "pingeur")

    # =========================
    # 🏰 Leaderboards par guilde
    # =========================
    teams = [t for t in get_teams(guild.id) if int(t["team_id"]) != 8]  # Exclure PRISME (id=8)
    for team in teams:
        key = f"guild_{int(team['team_id'])}"
        post = get_leaderboard_post(guild.id, key)
        msg = None
        if post:
            _, mid = post
            try:
                msg = await ch.fetch_message(mid)
            except discord.NotFound:
                msg = None

        emb = await build_guild_embed(bot, guild, team)

        if msg:
            await msg.edit(embed=emb)
        else:
            sent = await ch.send(embed=emb)
            set_leaderboard_post(guild.id, ch.id, sent.id, key)


class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ============================================================
    # ======= COMMANDE MANUELLE POUR RESET LEADERBOARDS ==========
    # ============================================================

    @app_commands.command(
        name="reset-leaderboards",
        description="Remet tous les leaderboards (sauf Pingeur) à zéro et met à jour les messages."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboards(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        # ⚠️ Reset complet SAUF pingeur
        reset_all_leaderboards(guild.id, exclude=["pingeur"])

        # Met à jour les leaderboards immédiatement
        await update_leaderboards(self.bot, guild)

        # Option : pousser un snapshot « vide » en passant par le cog existant (sans créer une nouvelle instance)
        try:
            snaps_cog = self.bot.get_cog("SnapshotsCog")
            if snaps_cog:
                payload = await snaps_cog._gather_snapshot_payload(guild)
                await snaps_cog._post_snapshot_file(guild, payload)
        except Exception:
            pass

        await interaction.followup.send("✅ Tous les leaderboards ont été remis à zéro (sauf Pingeur).", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
