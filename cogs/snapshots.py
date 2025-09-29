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
    seed_aggregates_dynamic,
    clear_baseline,
    get_guild_config,
    get_teams,            # dyn teams
    get_wins_by_user,     # 🆕
    get_losses_by_user,   # 🆕
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

        # Global & hourly
        w_all, l_all, inc_all, att_all = agg_totals_all(guild.id)
        m, a, s, n = hourly_split_all(guild.id)

        # Teams dyn
        teams = get_teams(guild.id)
        teams_block = {}
        for t in teams:
            tid = int(t["team_id"])
            w, l, inc, att = agg_totals_by_team(guild.id, tid)
            teams_block[str(tid)] = {"attacks": att, "wins": w, "losses": l, "incomplete": inc}

        # Compteurs par joueur (persistants)
        defense_by_user = get_leaderboard_totals_all(guild.id, "defense")
        ping_by_user    = get_leaderboard_totals_all(guild.id, "pingeur")
        wins_by_user    = get_wins_by_user(guild.id)     # calculés depuis messages+participants actuels
        losses_by_user  = get_losses_by_user(guild.id)

        payload = {
            "schema_version": 4,
            "guild_id": guild.id,
            "generated_at": paris_now_iso(),
            "global": {"attacks": att_all, "wins": w_all, "losses": l_all, "incomplete": inc_all},
            "teams": teams_block,  # clé = team_id (str)
            "hourly_buckets": {"morning": m, "afternoon": a, "evening": s, "night": n},
            "defense_by_user": defense_by_user,
            "ping_by_user": ping_by_user,
            "wins_by_user": wins_by_user,
            "losses_by_user": losses_by_user,
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

        if latest_json and int(latest_json.get("guild_id", 0)) == guild.id:
            # Snapshot (v4 dyn) ou compat v1/v2/v3
            global_tot = latest_json.get("global", {}) or {}

            # Teams dyn
            team_totals: dict[int, dict] = {}
            if "teams" in latest_json:
                for k, v in latest_json["teams"].items():
                    try:
                        team_totals[int(k)] = {kk: int(vv) for kk, vv in v.items()}
                    except Exception:
                        continue
            else:
                # Compat anciens snapshots (team_1..team_4)
                for i in (1, 2, 3, 4):
                    block = latest_json.get(f"team_{i}", None)
                    if block:
                        team_totals[i] = {kk: int(vv) for kk, vv in block.items()}

            hourly = latest_json.get("hourly_buckets", {}) or {}

            # Charger baseline depuis le snapshot (dyn)
            seed_aggregates_dynamic(guild.id, global_tot, team_totals, hourly)

            # Seed leaderboards (défenses / pings / wins / losses)
            def_tot = {int(k): int(v) for k, v in (latest_json.get("defense_by_user", {}) or {}).items()}
            ping_tot = {int(k): int(v) for k, v in (latest_json.get("ping_by_user", {}) or {}).items()}
            wins_tot = {int(k): int(v) for k, v in (latest_json.get("wins_by_user", {}) or {}).items()}
            loss_tot = {int(k): int(v) for k, v in (latest_json.get("losses_by_user", {}) or {}).items()}
            seed_leaderboard_totals(guild.id, "defense", def_tot)
            seed_leaderboard_totals(guild.id, "pingeur", ping_tot)
            seed_leaderboard_totals(guild.id, "win", wins_tot)
            seed_leaderboard_totals(guild.id, "loss", loss_tot)
        else:
            # Aucun snapshot -> baseline = 0
            clear_baseline(guild.id)

        from .leaderboard import update_leaderboards
        await update_leaderboards(self.bot, guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(SnapshotsCog(bot))
