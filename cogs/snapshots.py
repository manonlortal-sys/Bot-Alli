import json
import io
import asyncio
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands, tasks
from discord import app_commands

from storage import (
    get_guild_config,
    get_teams,
    agg_totals_all,
    agg_totals_by_team,
    hourly_split_all,
    get_leaderboard_totals_all,
    get_wins_by_user,
    get_losses_by_user,
    get_attacks_by_user_all,
    get_attacks_by_target_all,
    seed_leaderboard_totals,
    seed_aggregates_dynamic,
    seed_attack_user_totals,
    seed_attack_target_totals,
    clear_baseline,
    reset_leaderboard,
)
from cogs.leaderboard import update_leaderboards

# ============================================================
# =============== SNAPSHOTS COG ===============================
# ============================================================

def paris_now_iso() -> str:
    return datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds")


class SnapshotsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._restored_once = False
        self.weekly_reset_task.start()

    # ============================================================
    # =============== GÉNÉRATION SNAPSHOT =========================
    # ============================================================

    async def _gather_snapshot_payload(self, guild: discord.Guild) -> dict:
        """Rassemble toutes les données à sauvegarder dans le snapshot."""
        w_all, l_all, inc_all, att_all = agg_totals_all(guild.id)
        m, a, s, n = hourly_split_all(guild.id)

        teams = get_teams(guild.id)
        teams_block = {}
        for t in teams:
            tid = int(t["team_id"])
            w, l, inc, att = agg_totals_by_team(guild.id, tid)
            teams_block[str(tid)] = {"attacks": att, "wins": w, "losses": l, "incomplete": inc}

        defense_by_user = get_leaderboard_totals_all(guild.id, "defense")
        ping_by_user    = get_leaderboard_totals_all(guild.id, "pingeur")
        wins_by_user    = get_wins_by_user(guild.id)
        losses_by_user  = get_losses_by_user(guild.id)
        attacks_by_user   = get_attacks_by_user_all(guild.id)
        attacks_by_target = get_attacks_by_target_all(guild.id)

        payload = {
            "schema_version": 6,
            "guild_id": guild.id,
            "generated_at": paris_now_iso(),
            "global": {"attacks": att_all, "wins": w_all, "losses": l_all, "incomplete": inc_all},
            "teams": teams_block,
            "hourly_buckets": {"morning": m, "afternoon": a, "evening": s, "night": n},
            "defense_by_user": defense_by_user,
            "ping_by_user": ping_by_user,
            "wins_by_user": wins_by_user,
            "losses_by_user": losses_by_user,
            "attacks_by_user": attacks_by_user,
            "attacks_by_target": attacks_by_target,
        }
        return payload

    async def _post_snapshot_file(self, guild: discord.Guild, payload: dict):
        """Envoie le snapshot dans le canal configuré."""
        cfg = get_guild_config(guild.id)
        if not cfg:
            return
        channel = self.bot.get_channel(cfg["snapshot_channel_id"])
        if not channel:
            return

        json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        file_buf = io.BytesIO(json_str.encode("utf-8"))
        safe_ts = payload["generated_at"].replace(":", "-")
        filename = f"snapshot_{guild.id}_{safe_ts}.json"

        # Supprime l'ancien snapshot du bot
        async for m in channel.history(limit=20):
            if m.author.id == self.bot.user.id:
                try:
                    await m.delete()
                except Exception:
                    pass
                break

        await channel.send(
            content=f"📦 Snapshot sauvegardé — `{payload['generated_at']}`",
            file=discord.File(file_buf, filename=filename)
        )

    # ============================================================
    # =============== RESET HEBDOMADAIRE =========================
    # ============================================================

    @tasks.loop(minutes=1)
    async def weekly_reset_task(self):
        """Vérifie chaque minute si on est lundi à 00h00 heure de Paris."""
        now = datetime.now(ZoneInfo("Europe/Paris"))
        if now.weekday() == 0 and now.hour == 0 and now.minute == 0:
            print("🔁 Reset automatique des leaderboards (lundi 00h00)")
            for guild in self.bot.guilds:
                cfg = get_guild_config(guild.id)
                if not cfg:
                    continue
                # Reset uniquement les compteurs hebdos (pas pingeur)
                clear_baseline(guild.id)
                reset_leaderboard(guild.id, "defense")
                reset_leaderboard(guild.id, "win")
                reset_leaderboard(guild.id, "loss")
                await update_leaderboards(self.bot, guild)
            await asyncio.sleep(60)

    # ============================================================
    # =============== COMMANDE MANUELLE ==========================
    # ============================================================

    @app_commands.command(name="leaderboard-reset", description="🔄 Réinitialise tous les leaderboards (sauf pingeurs).")
    async def leaderboard_reset(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Commande à utiliser sur un serveur.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        clear_baseline(guild.id)
        reset_leaderboard(guild.id, "defense")
        reset_leaderboard(guild.id, "win")
        reset_leaderboard(guild.id, "loss")

        await update_leaderboards(self.bot, guild)
        await interaction.followup.send("✅ Tous les leaderboards ont été remis à zéro (sauf pingeurs).", ephemeral=False)

    # ============================================================
    # =============== RESTORE AUTO ===============================
    # ============================================================

    @commands.Cog.listener()
    async def on_ready(self):
        if self._restored_once:
            return
        self._restored_once = True

        for guild in self.bot.guilds:
            cfg = get_guild_config(guild.id)
            if not cfg:
                continue
            await update_leaderboards(self.bot, guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(SnapshotsCog(bot))
