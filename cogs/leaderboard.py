import discord
from discord.ext import commands, tasks
from discord import app_commands
from typing import Optional, Tuple, List
from zoneinfo import ZoneInfo
from datetime import datetime

from storage import (
    get_guild_config,
    get_teams,
    get_leaderboard_post,
    set_leaderboard_post,
    get_leaderboard_totals,
    agg_totals_by_team,
    reset_all_leaderboards,  # doit exister dans storage.py (tu l'as ajouté)
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
    """Prend le top global 'defense' depuis la DB et filtre par rôle de guilde."""
    lines: List[str] = []
    shown = 0
    for i, (uid, cnt) in enumerate(top):
        member = guild.get_member(uid)
        if not member:
            continue
        # filtre : uniquement les membres ayant le rôle de la guilde
        if team_role_id not in [r.id for r in member.roles]:
            continue

        if shown == 0:
            lines.append(f"🥇 {member.mention} — {cnt} défenses")
        elif shown == 1:
            lines.append(f"🥈 {member.mention} — {cnt} défenses")
        elif shown == 2:
            lines.append(f"🥉 {member.mention} — {cnt} défenses")
        else:
            lines.append(f"• {member.mention} — {cnt} défenses")

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
    """
    Récupère le message_id depuis la DB. S'il n'existe pas :
      1) tente de retrouver un message existant du bot dont l'embed commence par title_prefix,
      2) sinon crée le message et enregistre le post.
    Garantit qu'on réutilise toujours le même message (zéro duplication).
    """
    post = get_leaderboard_post(guild_id, storage_key)
    msg_id: Optional[int] = post[1] if post else None

    # a) si on a un id valide, on le renvoie (il sera fetch + édité par l'appelant)
    if msg_id:
        return int(msg_id)

    # b) sinon, scan court de l'historique pour retrouver un ancien message du bot
    async for m in channel.history(limit=50):
        if m.author.id != bot.user.id or not m.embeds:
            continue
        emb = m.embeds[0]
        if (emb.title or "").startswith(title_prefix):
            set_leaderboard_post(guild_id, channel.id, m.id, storage_key)
            return m.id

    # c) sinon, on crée le message une seule fois
    sent = await channel.send(embed=initial_embed)
    set_leaderboard_post(guild_id, channel.id, sent.id, storage_key)
    return sent.id


# ============================================================
# ================== BUILD DES EMBEDS ========================
# ============================================================

async def _build_guild_embed(guild: discord.Guild, team: dict) -> discord.Embed:
    """Embed d'une guilde : totaux + top défenseurs (depuis DB, filtrés par rôle)."""
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
    """Embed du leaderboard pingeurs (global, jamais reset)."""
    top_ping = get_leaderboard_totals(guild.id, "pingeur", limit=20)
    lines: List[str] = []
    for i, (uid, cnt) in enumerate(top_ping):
        if i == 0:
            lines.append(f"🥇 <@{uid}> — {cnt} pings")
        elif i == 1:
            lines.append(f"🥈 <@{uid}> — {cnt} pings")
        elif i == 2:
            lines.append(f"🥉 <@{uid}> — {cnt} pings")
        else:
            lines.append(f"• <@{uid}> — {cnt} pings")
    text = "\n".join(lines) if lines else "_Aucun pingeur encore_"

    em = discord.Embed(title="🛎️ Leaderboard Pingeurs", color=discord.Color.blurple())
    em.add_field(name="**Top Pingeurs**", value=text, inline=False)
    return em


# ============================================================
# ================== MISE À JOUR GLOBALE =====================
# ============================================================

async def update_leaderboards(bot: commands.Bot, guild: discord.Guild):
    """
    Met à jour :
      - un message par guilde (jamais recréé si déjà présent),
      - le message du leaderboard pingeurs (jamais recréé si déjà présent).
    """
    cfg = get_guild_config(guild.id)
    if not cfg:
        return
    ch = bot.get_channel(cfg["leaderboard_channel_id"])
    if not isinstance(ch, discord.TextChannel):
        return

    # --- Guildes (exclure PRISME id=8) ---
    teams = [t for t in get_teams(guild.id) if int(t["team_id"]) != 8]
    for t in teams:
        key = f"guild_{int(t['team_id'])}"
        emb = await _build_guild_embed(guild, t)

        # Obtenir ou créer une seule fois le message, puis l'éditer
        title_prefix = f"🏰 {t['name']}"
        msg_id = await _get_or_create_message_id(
            bot=bot,
            guild_id=guild.id,
            channel=ch,
            storage_key=key,
            title_prefix=title_prefix,
            initial_embed=emb
        )
        try:
            msg = await ch.fetch_message(msg_id)
            await msg.edit(embed=emb)
        except discord.NotFound:
            # Si le message a été supprimé manuellement, on le recrée proprement une seule fois
            sent = await ch.send(embed=emb)
            set_leaderboard_post(guild.id, ch.id, sent.id, key)

    # --- Pingeurs (global, jamais reset) ---
    ping_key = "pingeur"
    ping_emb = _build_pingeur_embed(guild)
    ping_title_prefix = "🛎️ Leaderboard Pingeurs"
    ping_msg_id = await _get_or_create_message_id(
        bot=bot,
        guild_id=guild.id,
        channel=ch,
        storage_key=ping_key,
        title_prefix=ping_title_prefix,
        initial_embed=ping_emb
    )
    try:
        msg = await ch.fetch_message(ping_msg_id)
        await msg.edit(embed=ping_emb)
    except discord.NotFound:
        sent = await ch.send(embed=ping_emb)
        set_leaderboard_post(guild.id, ch.id, sent.id, ping_key)


# ============================================================
# ======================= COG / COMMANDES ====================
# ============================================================

class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # reset auto chaque lundi 00h00 (Europe/Paris), sans toucher au type "pingeur"
        self._weekly_reset_task.start()

    # ---------- Reset manuel ----------
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
        # Reset complet (efface tout) SAUF type "pingeur"
        reset_all_leaderboards(guild.id, exclude=["pingeur"])
        await update_leaderboards(self.bot, guild)
        await interaction.followup.send("✅ Leaderboards remis à zéro (sauf Pingeur).", ephemeral=True)

    # ---------- Reset auto hebdomadaire ----------
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
            # on attend 60s pour éviter de répéter sur la même minute
            # (la loop est minute=1)
            await discord.utils.sleep_until(datetime.now(ZoneInfo("Europe/Paris")).replace(second=59))

    @_weekly_reset_task.before_loop
    async def _before_weekly_reset_task(self):
        await self.bot.wait_until_ready()

    # ---------- Mise à jour à la demande (optionnel, utile pour debug) ----------
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
