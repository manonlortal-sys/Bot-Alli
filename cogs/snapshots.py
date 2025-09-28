# cogs/snapshots.py
import json
from datetime import datetime, timezone
import discord
from discord.ext import commands
from discord import app_commands

from storage import (
    get_leaderboard_totals_all,
    agg_totals_all,
    agg_totals_by_team,
    hourly_split_all,
    seed_leaderboard_totals,
    seed_aggregates,
    get_guild_config,   # multi-serveur
)

def paris_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

class SnapshotsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._restored_once = False

    @app_commands.command(name="snapshot-save", description="Sauvegarder un snapshot des leaderboards et agrégats (manuel).")
    async def snapshot_save(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = get_guild_config(guild.id)
        if not cfg:
            await interaction.response.send_message("⚠️ Configuration manquante.", ephemeral=True)
            return

        channel = self.bot.get_channel(cfg["snapshot_channel_id"])
        if channel is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Canal snapshots introuvable.", ephemeral=True)
            return

        w_all, l_all, inc_all, att_all = agg_totals_all(guild.id)
        w_g1, l_g1, inc_g1, att_g1 = agg_totals_by_team(guild.id, 1)
        w_g2, l_g2, inc_g2, att_g2 = agg_totals_by_team(guild.id, 2)
        m, a, s, n = hourly_split_all(guild.id)

        defense_by_user = get_leaderboard_totals_all(guild.id, "defense")
        ping_by_user    = get_leaderboard_totals_all(guild.id, "pingeur")

        payload = {
            "schema_version": 1,
            "guild_id": guild.id,
            "generated_at": paris_now_iso(),
            "global": {"attacks": att_all, "wins": w_all, "losses": l_all, "incomplete": inc_all},
            "team_1": {"attacks": att_g1, "wins": w_g1, "losses": l_g1, "incomplete": inc_g1},
            "team_2": {"attacks": att_g2, "wins": w_g2, "losses": l_g2, "incomplete": inc_g2},
            "hourly_buckets": {"morning": m, "afternoon": a, "evening": s, "night": n},
            "defense_by_user": defense_by_user,
            "ping_by_user": ping_by_user
        }

        content = f"📦 Snapshot sauvegardé — `{payload['generated_at']}`\n```json\n{json.dumps(payload, ensure_ascii=False, separators=(',',':'))}\n```"
        await channel.send(content)
        await interaction.response.send_message("✅ Snapshot envoyé dans le canal dédié.", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._restored_once:
            return
        self._restored_once = True

        for guild in self.bot.guilds:
            cfg = get_guild_config(guild.id)
            if not cfg:
                continue
            await self._restore_latest_for_guild(guild, cfg["snapshot_channel_id"])

    async def _restore_latest_for_guild(self, guild: discord.Guild, snapshot_channel_id: int):
        channel = self.bot.get_channel(snapshot_channel_id)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return

        latest_json = None
        async for m in channel.history(limit=50):
            if m.author.id != self.bot.user.id or not m.content:
                continue
            if "```json" in m.content:
                try:
                    start = m.content.index("```json") + len("```json")
                    end = m.content.index("```", start)
                    json_str = m.content[start:end].strip()
                    latest_json = json.loads(json_str)
                    break
                except Exception:
                    continue
        if not latest_json or int(latest_json.get("guild_id", 0)) != guild.id:
            return

        seed_aggregates(guild.id, latest_json.get("global", {}), latest_json.get("team_1", {}), latest_json.get("team_2", {}), latest_json.get("hourly_buckets", {}))
        seed_leaderboard_totals(guild.id, "defense", {int(k): int(v) for k, v in latest_json.get("defense_by_user", {}).items()})
        seed_leaderboard_totals(guild.id, "pingeur", {int(k): int(v) for k, v in latest_json.get("ping_by_user", {}).items()})

        from .leaderboard import update_leaderboards
        await update_leaderboards(self.bot, guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(SnapshotsCog(bot))
