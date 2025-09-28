import discord
from discord.ext import commands

from storage import (
    get_leaderboard_post,
    set_leaderboard_post,
    get_leaderboard_totals,
    agg_totals_all,
    agg_totals_by_team,
    get_guild_config,
)

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
    w_g1, l_g1, inc_g1, att_g1 = agg_totals_by_team(guild.id, 1)
    w_g2, l_g2, inc_g2, att_g2 = agg_totals_by_team(guild.id, 2)
    w_g3, l_g3, inc_g3, att_g3 = agg_totals_by_team(guild.id, 3)
    w_g4, l_g4, inc_g4, att_g4 = agg_totals_by_team(guild.id, 4)

    embed_def = discord.Embed(title="📊 Leaderboard Défense", color=discord.Color.blue())
    embed_def.add_field(name="**🏆 Top défenseurs**", value=top_block, inline=False)

    name, value = separator_field()
    embed_def.add_field(name=name, value=value, inline=False)

    embed_def.add_field(name="**📌 Stats globales**", value=fmt_stats_block(att_all, w_all, l_all, inc_all), inline=False)

    name, value = separator_field()
    embed_def.add_field(name=name, value=value, inline=False)

    # 4 guildes : 2 colonnes x 2 lignes
    embed_def.add_field(name="**📌 Wanted**",   value=fmt_stats_block(att_g1, w_g1, l_g1, inc_g1), inline=True)
    embed_def.add_field(name="**📌 Wanted 2**", value=fmt_stats_block(att_g2, w_g2, l_g2, inc_g2), inline=True)
    embed_def.add_field(name="**📌 Snowflake**", value=fmt_stats_block(att_g3, w_g3, l_g3, inc_g3), inline=True)
    embed_def.add_field(name="**📌 Secteur K**", value=fmt_stats_block(att_g4, w_g4, l_g4, inc_g4), inline=True)

    # Forcer un saut propre après les colonnes
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


class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
