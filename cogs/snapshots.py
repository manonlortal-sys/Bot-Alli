# cogs/snapshots.py
import json
import io
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
    get_teams,
    get_wins_by_user,
    get_losses_by_user,
)

def paris_now_iso() -> str:
    # ISO local (Paris via tz système) sans microsecondes
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

class SnapshotsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._restored_once = False

    # =============== SAVE ===============
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

        # Supprimer le précédent snapshot du bot dans ce canal
        async for m in channel.history(limit=20):
            if m.author.id == self.bot.user.id:
                try:
                    await m.delete()
                except Exception:
                    pass
                break

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

        # Compteurs par joueur
        defense_by_user = get_leaderboard_totals_all(guild.id, "defense")
        ping_by_user    = get_leaderboard_totals_all(guild.id, "pingeur")
        wins_by_user    = get_wins_by_user(guild.id)
        losses_by_user  = get_losses_by_user(guild.id)

        payload = {
            "schema_version": 4,
            "guild_id": guild.id,
            "generated_at": paris_now_iso(),
            "global": {"attacks": att_all, "wins": w_all, "losses": l_all, "incomplete": inc_all},
            "teams": teams_block,
            "hourly_buckets": {"morning": m, "afternoon": a, "evening": s, "night": n},
            "defense_by_user": defense_by_user,
            "ping_by_user": ping_by_user,
            "wins_by_user": wins_by_user,
            "losses_by_user": losses_by_user,
        }

        # Envoi sous forme de fichier .json
        json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        file_buf = io.BytesIO(json_str.encode("utf-8"))
        safe_ts = payload["generated_at"].replace(":", "-")
        filename = f"snapshot_{guild.id}_{safe_ts}.json"

        await channel.send(
            content=f"📦 Snapshot sauvegardé — `{payload['generated_at']}`\n*(fichier .json en pièce jointe)*",
            file=discord.File(file_buf, filename=filename)
        )

        await interaction.response.send_message("✅ Snapshot envoyé dans le canal dédié.", ephemeral=True)

    # =============== RESTORE (AUTO AU DÉMARRAGE) ===============
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

        latest_payload = None

        # 1) Fichier .json attaché
        async for m in channel.history(limit=100):
            if m.author.id != self.bot.user.id:
                continue
            if m.attachments:
                for att in m.attachments:
                    if (att.filename or "").lower().endswith(".json"):
                        try:
                            data = await att.read()
                            latest_payload = json.loads(data.decode("utf-8"))
                            break
                        except Exception:
                            continue
                if latest_payload:
                    break

        # 2) Ancien format texte
        if latest_payload is None:
            async for m in channel.history(limit=100):
                if m.author.id != self.bot.user.id or not m.content:
                    continue
                if "```json" in m.content:
                    try:
                        start = m.content.index("```json") + len("```json")
                        end = m.content.index("```", start)
                        json_str = m.content[start:end].strip()
                        latest_payload = json.loads(json_str)
                        break
                    except Exception:
                        continue

        if latest_payload and int(latest_payload.get("guild_id", 0)) == guild.id:
            global_tot = latest_payload.get("global", {}) or {}
            team_totals: dict[int, dict] = {}
            if "teams" in latest_payload:
                for k, v in latest_payload["teams"].items():
                    try:
                        team_totals[int(k)] = {kk: int(vv) for kk, vv in v.items()}
                    except Exception:
                        continue
            else:
                for i in (1, 2, 3, 4):
                    block = latest_payload.get(f"team_{i}", None)
                    if block:
                        team_totals[i] = {kk: int(vv) for kk, vv in block.items()}

            hourly = latest_payload.get("hourly_buckets", {}) or {}

            # Charger baseline
            seed_aggregates_dynamic(guild.id, global_tot, team_totals, hourly)

            # Seed leaderboards
            def_tot = {int(k): int(v) for k, v in (latest_payload.get("defense_by_user", {}) or {}).items()}
            ping_tot = {int(k): int(v) for k, v in (latest_payload.get("ping_by_user", {}) or {}).items()}
            wins_tot = {int(k): int(v) for k, v in (latest_payload.get("wins_by_user", {}) or {}).items()}
            loss_tot = {int(k): int(v) for k, v in (latest_payload.get("losses_by_user", {}) or {}).items()}
            seed_leaderboard_totals(guild.id, "defense", def_tot)
            seed_leaderboard_totals(guild.id, "pingeur", ping_tot)
            seed_leaderboard_totals(guild.id, "win", wins_tot)
            seed_leaderboard_totals(guild.id, "loss", loss_tot)
        else:
            clear_baseline(guild.id)

        # MAJ des leaderboards
        import cogs.leaderboard as lb
        await lb.update_leaderboards(self.bot, guild)

async def setup(bot: commands.Bot):
    await bot.add_cog(SnapshotsCog(bot))
