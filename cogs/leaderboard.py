import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, List
from zoneinfo import ZoneInfo
from datetime import datetime

from storage import (
    get_guild_config,
    get_teams,
    get_leaderboard_post,
    set_leaderboard_post,
    get_leaderboard_totals,
    agg_totals_by_team,
    reset_all_leaderboards,
)

# ============================================================
# ================== HELPERS / FORMAT ========================
# ============================================================

def _format_top_defenders(
    top: List[tuple[int, int]],
    guild: discord.Guild,
    team_role_id: int,
    limit: int = 30
) -> str:
    lines: List[str] = []
    shown = 0
    for i, (uid, cnt) in enumerate(top):
        member = guild.get_member(uid)
        if not member or team_role_id not in [r.id for r in member.roles]:
            continue
        medal = ["🥇", "🥈", "🥉"][shown] if shown < 3 else "•"
        lines.append(f"{medal} {member.mention} — {cnt} défenses")
        shown += 1
        if shown >= limit:
            break
    return "\n".join(lines) if lines else "_Aucun défenseur encore_"


async def _get_or_create_message_id(
    bot: commands.Bot,
    guild_id: int,
    channel: discord.TextChannel,
    storage_key: str,
    title_prefix: str,
    initial_embed: discord.Embed
) -> int:
    post = get_leaderboard_post(guild_id, storage_key)
    msg_id: Optional[int] = post[1] if post else None
    if msg_id:
        return int(msg_id)
    async for m in channel.history(limit=50):
        if m.author.id != bot.user.id or not m.embeds:
            continue
        emb = m.embeds[0]
        if (emb.title or "").startswith(title_prefix):
            set_leaderboard_post(guild_id, channel.id, m.id, storage_key)
            return m.id
    sent = await channel.send(embed=initial_embed)
    set_leaderboard_post(guild_id, channel.id, sent.id, storage_key)
    return sent.id


# ============================================================
# ================== BUILD DES EMBEDS ========================
# ============================================================

async def _build_guild_embed(guild: discord.Guild, team: dict) -> discord.Embed:
    tid = int(team["team_id"])
    role_id = int(team["role_id"])
    w, l, inc, att = agg_totals_by_team(guild.id, tid)
    top_def_global = get_leaderboard_totals(guild.id, "defense", limit=200)
    defenders_block = _format_top_defenders(top_def_global, guild, role_id, limit=30)

    em = discord.Embed(
        title=f"🏰 {team['name']} — Leaderboard hebdomadaire",
        color=discord.Color.gold()
    )
    em.add_field(name="🗡️ Attaques", value=str(att), inline=True)
    em.add_field(name="🏆 Victoires", value=str(w), inline=True)
    em.add_field(name="❌ Défaites", value=str(l), inline=True)
    em.add_field(name="😡 Incomplètes", value=str(inc), inline=True)
    em.add_field(name="👥 Top défenseurs", value=defenders_block, inline=False)
    em.set_footer(text="Remis à zéro chaque lundi à 00h00 (Europe/Paris)")
    return em


def _build_pingeur_embed(guild: discord.Guild) -> discord.Embed:
    top_ping = get_leaderboard_totals(guild.id, "pingeur", limit=20)
    lines: List[str] = []
    for i, (uid, cnt) in enumerate(top_ping):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "•"
        lines.append(f"{medal} <@{uid}> — {cnt} pings")
    text = "\n".join(lines) if lines else "_Aucun pingeur encore_"
    em = discord.Embed(title="🛎️ Leaderboard Pingeurs", color=discord.Color.blurple())
    em.add_field(name="**Top Pingeurs**", value=text, inline=False)
    return em


# ============================================================
# ================== MISE À JOUR GLOBALE =====================
# ============================================================

async def safe_edit_message(msg: discord.Message, ch: discord.TextChannel, emb: discord.Embed, key: str, guild_id: int):
    """Édite un message avec gestion de la limite Discord (30046)."""
    try:
        await msg.edit(embed=emb)
    except discord.HTTPException as e:
        if e.code == 30046:  # trop d'édits sur message >1h
            try:
                await msg.delete()
            except Exception:
                pass
            sent = await ch.send(embed=emb)
            set_leaderboard_post(guild_id, ch.id, sent.id, key)
        else:
            raise


async def update_leaderboards(bot: commands.Bot, guild: discord.Guild):
    cfg = get_guild_config(guild.id)
    if not cfg:
        return
    ch = bot.get_channel(cfg["leaderboard_channel_id"])
    if not isinstance(ch, discord.TextChannel):
        return

    # --- Guildes ---
    teams = [t for t in get_teams(guild.id) if int(t["team_id"]) != 8]
    for t in teams:
        key = f"guild_{int(t['team_id'])}"
        emb = await _build_guild_embed(guild, t)
        title_prefix = f"🏰 {t['name']}"
        msg_id = await _get_or_create_message_id(bot, guild.id, ch, key, title_prefix, emb)
        try:
            msg = await ch.fetch_message(msg_id)
            await safe_edit_message(msg, ch, emb, key, guild.id)
        except discord.NotFound:
            sent = await ch.send(embed=emb)
            set_leaderboard_post(guild.id, ch.id, sent.id, key)

    # --- Pingeurs ---
    ping_key = "pingeur"
    ping_emb = _build_pingeur_embed(guild)
    ping_title_prefix = "🛎️ Leaderboard Pingeurs"
    ping_msg_id = await _get_or_create_message_id(bot, guild.id, ch, ping_key, ping_title_prefix, ping_emb)
    try:
        msg = await ch.fetch_message(ping_msg_id)
        await safe_edit_message(msg, ch, ping_emb, ping_key, guild.id)
    except discord.NotFound:
        sent = await ch.send(embed=ping_emb)
        set_leaderboard_post(guild.id, ch.id, sent.id, ping_key)


# ============================================================
# ======================= COG / COMMANDES ====================
# ============================================================

class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._weekly_reset_task.start()

    @app_commands.command(
        name="reset-leaderboards",
        description="Remet tous les leaderboards (sauf pingeur) à zéro et met à jour les messages."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboards_cmd(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        reset_all_leaderboards(guild.id, exclude=["pingeur"])
        await update_leaderboards(self.bot, guild)
        await interaction.followup.send("✅ Leaderboards remis à zéro (sauf Pingeur).", ephemeral=True)

    @tasks.loop(minutes=1)
    async def _weekly_reset_task(self):
        now = datetime.now(ZoneInfo("Europe/Paris"))
        if now.weekday() == 0 and now.hour == 0 and now.minute == 0:  # Lundi 00:00
            for g in self.bot.guilds:
                try:
                    reset_all_leaderboards(g.id, exclude=["pingeur"])
                    await update_leaderboards(self.bot, g)
                    print(f"[♻️] Reset hebdomadaire effectué pour {g.name}")
                except Exception as e:
                    print(f"[❌] Reset hebdo échoué pour {g.name}: {e}")
            await discord.utils.sleep_until(datetime.now(ZoneInfo("Europe/Paris")).replace(second=59))

    @_weekly_reset_task.before_loop
    async def _before_weekly_reset_task(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="leaderboards-refresh", description="Force la mise à jour des embeds de leaderboards.")
    @app_commands.checks.has_permissions(administrator=True)
    async def leaderboards_refresh(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ À utiliser dans un serveur.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        await update_leaderboards(self.bot, guild)
        await interaction.followup.send("🔄 Leaderboards rafraîchis.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
