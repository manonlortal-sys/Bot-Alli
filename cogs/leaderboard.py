import discord
from discord.ext import commands
from discord import app_commands

from storage import (
    get_leaderboard_post,
    set_leaderboard_post,
    get_leaderboard_totals,
    agg_totals_all,
    agg_totals_by_team,
    get_guild_config,
    get_teams,
    incr_leaderboard,
    decr_leaderboard,
    set_aggregate,
    get_aggregate,
)

# --------------------------------------------------
# Fonctions utilitaires pour l’affichage
# --------------------------------------------------
def medals_top_defenders(top: list[tuple[int, int]]) -> str:
    lines = []
    for i, (uid, cnt) in enumerate(top):
        if i == 0:
            lines.append(f"🥇 <@{uid}> : {cnt} défenses")
        elif i == 1:
            lines.append(f"🥈 <@{uid}> : {cnt} défenses")
        elif i == 2:
            lines.append(f"🥉 <@{uid}> : {cnt} défenses")
        else:
            lines.append(f"• <@{uid}> : {cnt} défenses")
    return "\n".join(lines) if lines else "_Aucun défenseur encore_"

def fmt_stats_block(att: int, w: int, l: int, inc: int) -> str:
    ratio = f"{(w/att*100):.1f}%" if att else "0%"
    return (
        f"\n"
        f"⚔️ Attaques : {att}\n"
        f"🏆 Victoires : {w}\n"
        f"❌ Défaites : {l}\n"
        f"😡 Incomplet : {inc}\n"
        f"📊 Ratio victoire : {ratio}\n"
    )

def separator_field() -> tuple[str, str]:
    return ("──────────", "\u200b")

# --------------------------------------------------
# Mise à jour des leaderboards
# --------------------------------------------------
async def update_leaderboards(bot: commands.Bot, guild: discord.Guild):
    cfg = get_guild_config(guild.id)
    if not cfg:
        return

    channel = bot.get_channel(cfg["leaderboard_channel_id"])
    if channel is None or not isinstance(channel, discord.TextChannel):
        return

    # ---------- Leaderboard Défense ----------
    def_post = get_leaderboard_post(guild.id, "defense")
    if def_post:
        try:
            msg_def = await channel.fetch_message(def_post[1])
        except discord.NotFound:
            msg_def = await channel.send("📊 **Leaderboard Défense**")
            set_leaderboard_post(guild.id, channel.id, msg_def.id, "defense")
    else:
        msg_def = await channel.send("📊 **Leaderboard Défense**")
        set_leaderboard_post(guild.id, channel.id, msg_def.id, "defense")

    top_def = get_leaderboard_totals(guild.id, "defense", limit=100)
    top_block = medals_top_defenders(top_def)

    w_all, l_all, inc_all, att_all = agg_totals_all(guild.id)

    embed_def = discord.Embed(title="📊 Leaderboard Défense", color=discord.Color.blue())
    embed_def.add_field(name="**🏆 Top défenseurs**", value=top_block, inline=False)

    name, value = separator_field()
    embed_def.add_field(name=name, value=value, inline=False)

    embed_def.add_field(name="**📌 Stats globales**", value=fmt_stats_block(att_all, w_all, l_all, inc_all), inline=False)

    name, value = separator_field()
    embed_def.add_field(name=name, value=value, inline=False)

    # Stats par équipe dynamiques (ordre = order_index de team_config)
    teams = get_teams(guild.id)
    for t in teams:
        tid = int(t["team_id"])
        w, l, inc, att = agg_totals_by_team(guild.id, tid)
        embed_def.add_field(name=f"**📌 {t['name']}**", value=fmt_stats_block(att, w, l, inc), inline=True)

    # ligne blanche pour forcer le saut si nombre impair
    embed_def.add_field(name="\u200b", value="\u200b", inline=False)

    await msg_def.edit(embed=embed_def)

    # ---------- Leaderboard Pingeurs ----------
    ping_post = get_leaderboard_post(guild.id, "pingeur")
    if ping_post:
        try:
            msg_ping = await channel.fetch_message(ping_post[1])
        except discord.NotFound:
            msg_ping = await channel.send("📊 **Leaderboard Pingeurs**")
            set_leaderboard_post(guild.id, channel.id, msg_ping.id, "pingeur")
    else:
        msg_ping = await channel.send("📊 **Leaderboard Pingeurs**")
        set_leaderboard_post(guild.id, channel.id, msg_ping.id, "pingeur")

    top_ping = get_leaderboard_totals(guild.id, "pingeur", limit=100)
    ping_lines = []
    for i, (uid, cnt) in enumerate(top_ping):
        if i == 0:
            ping_lines.append(f"🥇 <@{uid}> : {cnt} pings")
        elif i == 1:
            ping_lines.append(f"🥈 <@{uid}> : {cnt} pings")
        elif i == 2:
            ping_lines.append(f"🥉 <@{uid}> : {cnt} pings")
        else:
            ping_lines.append(f"• <@{uid}> : {cnt} pings")
    ping_block = "\n".join(ping_lines) if ping_lines else "_Aucun pingeur encore_"

    embed_ping = discord.Embed(title="📊 Leaderboard Pingeurs", color=discord.Color.gold())
    embed_ping.add_field(name="**🏅 Top pingeurs**", value=ping_block, inline=False)
    await msg_ping.edit(embed=embed_ping)

# --------------------------------------------------
# Cog + Commandes d'ajustement (avec autocomplétion)
# --------------------------------------------------
PLAYER_COUNTER_CHOICES = ["defense", "pingeur", "win", "loss"]
TEAM_COUNTER_CHOICES = ["attacks", "wins", "losses", "incomplete"]

class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Helpers permissions ----------
    def _is_admin(self, interaction: discord.Interaction) -> bool:
        cfg = get_guild_config(interaction.guild.id) if interaction.guild else None
        if not cfg:
            return False
        admin_role_id = cfg.get("admin_role_id")
        if not admin_role_id:
            return False
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        return bool(member and any(r.id == admin_role_id for r in member.roles))

    # ---------- Autocomplétion Team ----------
    async def _team_choices(self, interaction: discord.Interaction, current: str):
        choices: list[app_commands.Choice[int]] = []
        if not interaction.guild:
            return choices
        q = (current or "").lower()
        for t in get_teams(interaction.guild.id):
            label = str(t["name"])
            tid = int(t["team_id"])
            if not q or q in label.lower():
                # name = affiché, value = team_id (int)
                choices.append(app_commands.Choice(name=label, value=tid))
            if len(choices) >= 25:
                break
        return choices

    # ---------- /adjust-player ----------
    @app_commands.command(name="adjust-player", description="Corriger manuellement un compteur pour un joueur (admin).")
    @app_commands.describe(
        member="Joueur à corriger",
        counter="Type de compteur : defense, pingeur, win, loss",
        amount="Valeur à ajouter (positif) ou retirer (négatif), ex: -3, 2"
    )
    @app_commands.choices(
        counter=[app_commands.Choice(name=c, value=c) for c in PLAYER_COUNTER_CHOICES]
    )
    async def adjust_player(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        counter: app_commands.Choice[str],
        amount: int
    ):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Tu n’as pas la permission.", ephemeral=True)
            return

        # Ajustement
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

    # ---------- /adjust-team ----------
    @app_commands.command(name="adjust-team", description="Corriger manuellement un compteur pour une équipe (admin).")
    @app_commands.describe(
        team="Nom de l’équipe (autocomplétion)",
        counter="Type : attacks, wins, losses, incomplete",
        amount="Valeur à ajouter (positif) ou retirer (négatif), ex: -4, 3"
    )
    @app_commands.choices(
        counter=[app_commands.Choice(name=c, value=c) for c in TEAM_COUNTER_CHOICES]
    )
    async def adjust_team(
        self,
        interaction: discord.Interaction,
        team: int,
        counter: app_commands.Choice[str],
        amount: int
    ):
        if not self._is_admin(interaction):
            await interaction.response.send_message("❌ Tu n’as pas la permission.", ephemeral=True)
            return

        scope = f"team:{int(team)}"
        current_val = get_aggregate(interaction.guild.id, scope, counter.value)
        new_val = current_val + amount
        if new_val < 0:
            new_val = 0  # on évite les valeurs négatives

        set_aggregate(interaction.guild.id, scope, counter.value, new_val)

        await update_leaderboards(self.bot, interaction.guild)
        sign = "+" if amount >= 0 else ""
        # retrouver le nom affichable
        teams = {int(t["team_id"]): str(t["name"]) for t in get_teams(interaction.guild.id)}
        team_name = teams.get(int(team), f"Team {team}")
        await interaction.response.send_message(
            f"✅ `{counter.value}` ajusté de **{sign}{amount}** pour **{team_name}**. (nouvelle valeur base = {new_val})",
            ephemeral=False
        )

    @adjust_team.autocomplete("team")
    async def adjust_team_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._team_choices(interaction, current)

# --------------------------------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
