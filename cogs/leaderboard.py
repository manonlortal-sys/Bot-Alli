import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import pytz

from storage import (
    get_leaderboard_post,
    set_leaderboard_post,
    get_leaderboard_totals,
    agg_totals_by_team,
    get_guild_config,
    get_teams,
    incr_leaderboard,
    decr_leaderboard,
    set_aggregate,
    get_aggregate,
    reset_all_leaderboards,  # à ajouter dans storage : efface toutes les données sauf pingeurs
)

# --------------------------------------------------
# Fonctions utilitaires
# --------------------------------------------------

def medals_top_defenders(top: list[tuple[int, int]]) -> str:
    lines = []
    for i, (uid, cnt) in enumerate(top):
        if i == 0:
            lines.append(f"🥇 <@{uid}> — {cnt} défenses")
        elif i == 1:
            lines.append(f"🥈 <@{uid}> — {cnt} défenses")
        elif i == 2:
            lines.append(f"🥉 <@{uid}> — {cnt} défenses")
        else:
            lines.append(f"• <@{uid}> — {cnt} défenses")
    return "\n".join(lines) if lines else "_Aucun défenseur encore_"

def fmt_stats_block(att: int, w: int, l: int, inc: int) -> str:
    return (
        f"🗡️ Attaques : {att}\n"
        f"🏆 Victoires : {w}\n"
        f"❌ Défaites : {l}\n"
        f"😡 Défenses incomplètes : {inc}"
    )

def separator_field() -> tuple[str, str]:
    return ("──────────", "\u200b")

def _limit_list_field(lines: list[str]) -> str:
    """Coupe proprement pour rester < 1024 chars."""
    out = []
    for s in lines:
        if len("\n".join(out + [s])) > 1000:
            out.append("…")
            break
        out.append(s)
    return "\n".join(out) if out else "—"

# --------------------------------------------------
# Fonction principale : mise à jour des leaderboards
# --------------------------------------------------

async def update_leaderboards(bot: commands.Bot, guild: discord.Guild):
    """Met à jour le leaderboard pingeurs + un embed par guilde (Wanted, HagraTime, etc.)."""
    from cogs.alerts import TEAM_EMOJIS

    cfg = get_guild_config(guild.id)
    if not cfg:
        return

    channel = bot.get_channel(cfg["leaderboard_channel_id"])
    if channel is None or not isinstance(channel, discord.TextChannel):
        return

    # ====================================================
    # 🛎️ Leaderboard PINGEURS (inchangé)
    # ====================================================
    ping_post = get_leaderboard_post(guild.id, "pingeur")
    if ping_post:
        try:
            msg_ping = await channel.fetch_message(ping_post[1])
        except discord.NotFound:
            msg_ping = await channel.send("🛎️ **Leaderboard Pingeurs**")
            set_leaderboard_post(guild.id, channel.id, msg_ping.id, "pingeur")
    else:
        msg_ping = await channel.send("🛎️ **Leaderboard Pingeurs**")
        set_leaderboard_post(guild.id, channel.id, msg_ping.id, "pingeur")

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
    ping_block = _limit_list_field(ping_lines) or "_Aucun pingeur encore_"

    embed_ping = discord.Embed(title="🛎️ Leaderboard Pingeurs", color=discord.Color.gold())
    embed_ping.add_field(name="**Top Pingeurs**", value=ping_block, inline=False)
    await msg_ping.edit(embed=embed_ping)

    # ====================================================
    # 🏰 Leaderboards par GUILDE
    # ====================================================
    teams = [t for t in get_teams(guild.id) if int(t["team_id"]) != 8]  # exclure Prisme

    for team in teams:
        tid = int(team["team_id"])
        team_name = str(team["name"])
        emoji = TEAM_EMOJIS.get(tid)
        emoji_str = f"{emoji} " if emoji else ""

        post_key = f"guild_{tid}"
        guild_post = get_leaderboard_post(guild.id, post_key)

        if guild_post:
            try:
                msg_guild = await channel.fetch_message(guild_post[1])
            except discord.NotFound:
                msg_guild = await channel.send(f"{emoji_str}**{team_name} — Leaderboard hebdomadaire**")
                set_leaderboard_post(guild.id, channel.id, msg_guild.id, post_key)
        else:
            msg_guild = await channel.send(f"{emoji_str}**{team_name} — Leaderboard hebdomadaire**")
            set_leaderboard_post(guild.id, channel.id, msg_guild.id, post_key)

        # Récup stats
        w, l, inc, att = agg_totals_by_team(guild.id, tid)
        stats_block = fmt_stats_block(att, w, l, inc)

        # Récup top défenseurs (≥ 1 défense)
        top_def = get_leaderboard_totals(guild.id, "defense", limit=50)
        def_lines = []
        for i, (uid, cnt) in enumerate(top_def):
            member = guild.get_member(uid)
            if not member:
                continue
            # Filtrer par rôle de la guilde
            if not any(r.id == int(team["role_id"]) for r in member.roles):
                continue
            if cnt <= 0:
                continue
            if i == 0:
                def_lines.append(f"🥇 <@{uid}> — {cnt} défenses")
            elif i == 1:
                def_lines.append(f"🥈 <@{uid}> — {cnt} défenses")
            elif i == 2:
                def_lines.append(f"🥉 <@{uid}> — {cnt} défenses")
            else:
                def_lines.append(f"• <@{uid}> — {cnt} défenses")

        def_block = _limit_list_field(def_lines) or "_Aucun défenseur encore_"

        embed_guild = discord.Embed(
            title=f"{emoji_str}{team_name} — Leaderboard hebdomadaire",
            color=discord.Color.from_rgb(200, 50, 50)
        )
        embed_guild.add_field(name="📊 Statistiques", value=stats_block, inline=False)

        name, value = separator_field()
        embed_guild.add_field(name=name, value=value, inline=False)

        embed_guild.add_field(name="👥 Top défenseurs", value=def_block, inline=False)

        await msg_guild.edit(embed=embed_guild)


# --------------------------------------------------
# Tâche planifiée : reset hebdomadaire (lundi 00h00)
# --------------------------------------------------

class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reset_task.start()

    def cog_unload(self):
        self.reset_task.cancel()

    @tasks.loop(hours=1)
    async def reset_task(self):
        """Vérifie chaque heure si on est lundi 00h00 (heure de Paris) pour reset les stats."""
        tz = pytz.timezone("Europe/Paris")
        now = datetime.now(tz)

        if now.weekday() == 0 and now.hour == 0:  # Lundi 00h00
            print("[♻️] Reset hebdomadaire des leaderboards")
            await self.perform_weekly_reset()

    async def perform_weekly_reset(self):
        """Remet à zéro toutes les stats (sauf pingeurs)."""
        for guild in self.bot.guilds:
            try:
                reset_all_leaderboards(guild.id, exclude=["pingeur"])
                await update_leaderboards(self.bot, guild)
                print(f"[✅] Reset effectué pour {guild.name}")
            except Exception as e:
                print(f"[❌] Erreur reset {guild.name}: {e}")

    @reset_task.before_loop
    async def before_reset_task(self):
        await self.bot.wait_until_ready()
        print("⏰ Tâche de reset hebdomadaire prête.")

    # ---------- /adjust-player ----------
    @app_commands.command(name="adjust-player", description="Corriger manuellement un compteur pour un joueur (admin).")
    @app_commands.describe(
        member="Joueur à corriger",
        counter="Type de compteur : defense, pingeur, win, loss",
        amount="Valeur à ajouter (positif) ou retirer (négatif)"
    )
    @app_commands.choices(
        counter=[app_commands.Choice(name=c, value=c) for c in ["defense", "pingeur", "win", "loss"]]
    )
    async def adjust_player(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        counter: app_commands.Choice[str],
        amount: int
    ):
        cfg = get_guild_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message("⚠️ Configuration manquante.", ephemeral=True)
            return

        admin_role_id = cfg.get("admin_role_id")
        if not admin_role_id or not any(r.id == admin_role_id for r in interaction.user.roles):
            await interaction.response.send_message("❌ Tu n’as pas la permission.", ephemeral=True)
            return

        if amount > 0:
            for _ in range(amount):
                incr_leaderboard(interaction.guild.id, counter.value, member.id)
        elif amount < 0:
            for _ in range(-amount):
                decr_leaderboard(interaction.guild.id, counter.value, member.id)

        await update_leaderboards(self.bot, interaction.guild)
        sign = "+" if amount >= 0 else ""
        await interaction.response.send_message(
            f"✅ `{counter.value}` ajusté de **{sign}{amount}** pour {member.mention}.",
            ephemeral=False
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))

