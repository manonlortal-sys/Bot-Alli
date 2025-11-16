import discord
from discord.ext import commands
from discord import app_commands
from typing import List

from storage import (
    get_guild_config,
    get_teams,
    get_leaderboard_totals,
    get_leaderboard_value,
    agg_totals_by_team,
    set_leaderboard_post,
    get_leaderboard_post,
)

# Teams à exclure
EXCLUDED_TEAMS = {0, 8}  # 0 = test, 8 = prisme


# ------------------------------------------------------------
# 🔧 Helpers
# ------------------------------------------------------------

def _format_top_defenders(guild: discord.Guild, top: List[tuple[int, int]]) -> str:
    lines = []
    for i, (uid, cnt) in enumerate(top[:20]):
        member = guild.get_member(uid)
        if not member:
            continue
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "•"
        lines.append(f"{medal} {member.mention} — {cnt}")
    return "\n".join(lines) if lines else "_Aucun défenseur pour l’instant_"


def _format_guild_block(guild_id: int, teams: list, exclude: set) -> str:
    lines = []
    for t in teams:
        tid = int(t["team_id"])
        if tid in exclude:
            continue

        w, l, inc, att = agg_totals_by_team(guild_id, tid)
        name = t["name"]

        lines.append(
            f"### 🏰 {name}\n"
            f"- Défenses : **{att}**\n"
            f"- Victoires : **{w}**\n"
            f"- Défaites : **{l}**\n"
            f"- Incomplètes : **{inc}**\n"
        )

    return "\n".join(lines) if lines else "_Aucune guilde enregistrée_"


async def _edit_or_create(bot, guild: discord.Guild, channel: discord.TextChannel, storage_key: str, embed: discord.Embed):
    """Édite le message déjà existant. Ne crée jamais de nouveau message sauf première fois."""
    post = get_leaderboard_post(guild.id, storage_key)

    if post:
        msg_id = post[1]
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed)
            return
        except discord.NotFound:
            pass

    # Première création
    sent = await channel.send(embed=embed)
    set_leaderboard_post(guild.id, channel.id, sent.id, storage_key)


# ------------------------------------------------------------
# 🔥 Build embeds
# ------------------------------------------------------------

async def build_defense_embed(guild: discord.Guild) -> discord.Embed:
    top_def = get_leaderboard_totals(guild.id, "defense", limit=200)
    teams = [t for t in get_teams(guild.id) if int(t["team_id"]) not in EXCLUDED_TEAMS]

    embed = discord.Embed(
        title="🛡️ Leaderboard Défenses",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="🏆 Top 20 Défenseurs",
        value=_format_top_defenders(guild, top_def),
        inline=False
    )

    guild_stats_block = _format_guild_block(guild.id, teams, EXCLUDED_TEAMS)
    embed.add_field(
        name="📊 Statistiques par Guilde",
        value=guild_stats_block,
        inline=False
    )

    return embed


async def build_ping_embed(guild: discord.Guild) -> discord.Embed:
    top_ping = get_leaderboard_totals(guild.id, "pingeur", limit=20)

    lines = []
    for i, (uid, cnt) in enumerate(top_ping):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "•"
        lines.append(f"{medal} <@{uid}> — {cnt}")

    text = "\n".join(lines) if lines else "_Aucun ping pour l’instant_"

    embed = discord.Embed(
        title="🛎️ Leaderboard Pingeurs",
        color=discord.Color.blue()
    )
    embed.add_field(name="Top Pingeurs", value=text, inline=False)

    return embed


# ------------------------------------------------------------
# 🔁 Mise à jour globale
# ------------------------------------------------------------

async def update_leaderboards(bot: commands.Bot, guild: discord.Guild):
    cfg = get_guild_config(guild.id)
    if not cfg:
        return

    channel = bot.get_channel(cfg["leaderboard_channel_id"])
    if not isinstance(channel, discord.TextChannel):
        return

    # DEFENSES
    def_embed = await build_defense_embed(guild)
    await _edit_or_create(bot, guild, channel, "leaderboard_def", def_embed)

    # PINGEURS
    ping_embed = await build_ping_embed(guild)
    await _edit_or_create(bot, guild, channel, "leaderboard_ping", ping_embed)


# ------------------------------------------------------------
# 🎛️ Cog
# ------------------------------------------------------------

class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leaderboards-refresh", description="Forcer la mise à jour des leaderboards.")
    @app_commands.checks.has_permissions(administrator=True)
    async def refresh_lb(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await update_leaderboards(self.bot, interaction.guild)
        await interaction.followup.send("🔄 Leaderboards mis à jour.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
