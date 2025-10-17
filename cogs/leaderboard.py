import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from storage import (
    get_guild_config,
    get_teams,
    get_leaderboard_post,
    set_leaderboard_post,
    get_leaderboard_totals,
    agg_totals_by_team,
    clear_baseline,
)

# ============================================================
# ============= LEADERBOARD COG (PAR GUILDE) =================
# ============================================================

def medals_top_defenders(top: list[tuple[int, int]], guild: discord.Guild, team_role: int) -> str:
    """Retourne un bloc formaté des meilleurs défenseurs d'une guilde donnée."""
    lines = []
    for i, (uid, cnt) in enumerate(top):
        member = guild.get_member(uid)
        if not member or team_role not in [r.id for r in member.roles]:
            continue  # On affiche uniquement ceux appartenant à cette guilde
        if i == 0:
            lines.append(f"🥇 {member.mention} — {cnt} défenses")
        elif i == 1:
            lines.append(f"🥈 {member.mention} — {cnt} défenses")
        elif i == 2:
            lines.append(f"🥉 {member.mention} — {cnt} défenses")
        else:
            lines.append(f"• {member.mention} — {cnt} défenses")

    return "\n".join(lines) if lines else "_Aucun défenseur enregistré_"


async def build_guild_embed(bot, guild, team):
    """Construit un embed de leaderboard pour une guilde précise."""
    w, l, inc, att = agg_totals_by_team(guild.id, team["team_id"])
    top_def = get_leaderboard_totals(guild.id, "defense", limit=100)
    defenders_text = medals_top_defenders(top_def, guild, team["role_id"])

    emb = discord.Embed(
        title=f"🏰 {team['name']} — Leaderboard",
        color=discord.Color.gold()
    )
    emb.add_field(name="⚔️ Défenses totales", value=str(att), inline=True)
    emb.add_field(name="🏆 Victoires", value=str(w), inline=True)
    emb.add_field(name="💀 Défaites", value=str(l), inline=True)
    emb.add_field(name="😡 Défenses incomplètes", value=str(inc), inline=True)
    emb.add_field(name="🧙 Défenseurs", value=defenders_text, inline=False)
    emb.set_footer(text="Remis à zéro chaque lundi à 00h00 (heure de Paris)")
    return emb


async def build_pingeur_embed(guild):
    """Construit le leaderboard global des pingeurs."""
    top_ping = get_leaderboard_totals(guild.id, "pingeur", limit=20)
    lines = []
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
    emb = discord.Embed(title="🛎️ Leaderboard Pingeurs", color=discord.Color.blurple())
    emb.add_field(name="**Top Pingeurs**", value=text, inline=False)
    return emb


async def update_leaderboards(bot, guild):
    """Met à jour tous les leaderboards par guilde + pingeur."""
    cfg = get_guild_config(guild.id)
    if not cfg:
        return

    lb_channel = bot.get_channel(cfg["leaderboard_channel_id"])
    if not lb_channel:
        return

    # 🔹 Leaderboards de guildes
    teams = get_teams(guild.id)
    for team in teams:
        if team["name"].lower() == "prisme":
            continue

        emb = await build_guild_embed(bot, guild, team)
        post = get_leaderboard_post(guild.id, f"guild_{team['team_id']}")
        channel_id, message_id = post if post else (None, None)

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

    # 🔹 Leaderboard PINGEUR global
    emb_ping = await build_pingeur_embed(guild)
    post_ping = get_leaderboard_post(guild.id, "pingeur")
    channel_id, message_id = post_ping if post_ping else (None, None)

    try:
        if message_id:
            msg = await lb_channel.fetch_message(message_id)
            await msg.edit(embed=emb_ping)
        else:
            msg = await lb_channel.send(embed=emb_ping)
            set_leaderboard_post(guild.id, lb_channel.id, msg.id, "pingeur")
    except Exception:
        try:
            msg = await lb_channel.send(embed=emb_ping)
            set_leaderboard_post(guild.id, lb_channel.id, msg.id, "pingeur")
        except Exception:
            pass


class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_reset_task.start()  # 🚀 Démarre la tâche auto

    @app_commands.command(name="reset-leaderboards", description="Remet tous les leaderboards (sauf pingeur) à zéro et les met à jour.")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_leaderboards(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        clear_baseline(guild.id)
        await update_leaderboards(self.bot, guild)
        await interaction.followup.send("✅ Tous les leaderboards ont été remis à zéro (sauf Pingeur).", ephemeral=True)

    # ============================================================
    # =============== RÉINITIALISATION AUTO ======================
    # ============================================================

    @tasks.loop(hours=1)
    async def weekly_reset_task(self):
        """Vérifie chaque heure si on est lundi 00h00 (heure de Paris)."""
        now = datetime.now(ZoneInfo("Europe/Paris"))
        if now.weekday() == 0 and now.hour == 0:  # Lundi minuit
            for guild in self.bot.guilds:
                try:
                    clear_baseline(guild.id)
                    await update_leaderboards(self.bot, guild)
                    print(f"🔁 Leaderboards remis à zéro automatiquement pour {guild.name}")
                except Exception as e:
                    print(f"⚠️ Erreur reset auto {guild.name}: {e}")

    @weekly_reset_task.before_loop
    async def before_weekly_reset(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
