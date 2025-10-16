# cogs/snapshots.py
import json
import io
import asyncio
from datetime import datetime, timezone, timedelta
import discord
from discord.ext import commands, tasks
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
    # --- Attaques ---
    get_attacks_by_user_all,
    get_attacks_by_target_all,
    seed_attack_user_totals,
    seed_attack_target_totals,
    # --- Défenses (needed for rattrapage) ---
    is_tracked_message,
    upsert_message,
    add_participant,
    incr_leaderboard,
    set_outcome,
    set_incomplete,
)

ALERTS_CHANNEL_ID = 1139550892471889971
ATTACKS_CHANNEL_ID = 1308517556193071154
SNAPSHOT_CHANNEL_ID = 1421866144679329984

def paris_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def parse_iso_to_dt(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso)
    except Exception:
        return datetime.now(timezone.utc)

class SnapshotsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._restored_once = False
        self._hourly_task = None
        self._running_snapshot = asyncio.Lock()

    # =============== SAVE (internal helper) ===============
    async def _gather_snapshot_payload(self, guild: discord.Guild) -> dict:
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
        channel = self.bot.get_channel(SNAPSHOT_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return
        json_str = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        file_buf = io.BytesIO(json_str.encode("utf-8"))
        safe_ts = payload["generated_at"].replace(":", "-")
        filename = f"snapshot_{guild.id}_{safe_ts}.json"
        # delete previous bot snapshot (keep last 1)
        async for m in channel.history(limit=20):
            if m.author.id == self.bot.user.id:
                try:
                    await m.delete()
                except Exception:
                    pass
                break
        await channel.send(
            content=f"📦 Snapshot sauvegardé — `{payload['generated_at']}`\n*(fichier .json en pièce jointe)*",
            file=discord.File(file_buf, filename=filename)
        )

    # =============== RATTRAPAGE (lire messages entre last_snapshot et now) ===============
    async def _find_last_snapshot_time(self, guild: discord.Guild) -> datetime:
        channel = self.bot.get_channel(SNAPSHOT_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return datetime.now(timezone.utc) - timedelta(days=365)
        async for m in channel.history(limit=200):
            if m.author.id != self.bot.user.id:
                continue
            # try attachments first
            if m.attachments:
                for att in m.attachments:
                    if (att.filename or "").lower().endswith(".json"):
                        try:
                            data = await att.read()
                            latest_payload = json.loads(data.decode("utf-8"))
                            gen = latest_payload.get("generated_at")
                            if gen:
                                return parse_iso_to_dt(gen)
                        except Exception:
                            continue
            # fallback: inline json
            if m.content and "```json" in m.content:
                try:
                    start = m.content.index("```json") + len("```json")
                    end = m.content.index("```", start)
                    json_str = m.content[start:end].strip()
                    latest_payload = json.loads(json_str)
                    gen = latest_payload.get("generated_at")
                    if gen:
                        return parse_iso_to_dt(gen)
                except Exception:
                    continue
        # if none found, return epoch-ish
        return datetime.now(timezone.utc) - timedelta(days=365)

    async def _rattrapage_defenses(self, guild: discord.Guild, since: datetime):
        channel = self.bot.get_channel(ALERTS_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return
        async for m in channel.history(limit=500, after=since):
            # consider only messages by anyone (could be bot or users)
            # check embeds for title starting with "🛡️ Alerte Attaque"
            if not m.embeds:
                continue
            emb = m.embeds[0]
            title = (emb.title or "")
            if not title.startswith("🛡️ Alerte Attaque"):
                continue
            # if already tracked, skip
            if is_tracked_message(m.id):
                continue
            # upsert message minimal
            try:
                upsert_message(m.id, m.guild.id, m.channel.id, int(m.created_at.timestamp()), creator_id=m.author.id)
            except Exception:
                pass
            # parse defenders block: find field named starting with "Défenseurs"
            defenders = []
            for f in emb.fields:
                if f.name and "Défenseurs" in f.name:
                    lines = f.value.splitlines()
                    for line in lines:
                        line = line.strip()
                        if line.startswith("•"):
                            name_part = line[1:].strip()
                            # attempt to extract a mention <@...>
                            # if mention present, discord will render as <@id> in raw; otherwise keep text
                            # we only add participants if we can extract an ID via <@...>
                            if "<@" in name_part:
                                # extract all <@...> patterns
                                parts = []
                                tokens = name_part.split()
                                for tok in tokens:
                                    if tok.startswith("<@") and tok.endswith(">"):
                                        try:
                                            uid = int(tok.replace("<@!", "").replace("<@", "").replace(">", ""))
                                            defenders.append(uid)
                                        except Exception:
                                            continue
                            else:
                                # try to find a member by display name (best-effort)
                                # fallback: ignore if no mention
                                continue
            # add participants
            for uid in defenders:
                try:
                    inserted = add_participant(m.id, uid, None, "rattrapage")
                    if inserted:
                        incr_leaderboard(guild.id, "defense", uid)
                except Exception:
                    pass
            # set outcome from reactions if any
            try:
                reactions = {str(r.emoji): r.count for r in m.reactions}
                win = "🏆" in reactions and reactions["🏆"] > 0
                loss = "❌" in reactions and reactions["❌"] > 0
                inc = "😡" in reactions and reactions["😡"] > 0
                if win and not loss:
                    set_outcome(m.id, "win")
                    # credit wins to participants
                    for uid in defenders:
                        try:
                            incr_leaderboard(guild.id, "win", uid)
                        except Exception:
                            pass
                elif loss and not win:
                    set_outcome(m.id, "loss")
                    for uid in defenders:
                        try:
                            incr_leaderboard(guild.id, "loss", uid)
                        except Exception:
                            pass
                else:
                    set_outcome(m.id, None)
                set_incomplete(m.id, inc)
                # credit pingeur (creator) once
                try:
                    incr_leaderboard(guild.id, "pingeur", m.author.id)
                except Exception:
                    pass
            except Exception:
                pass

    async def _rattrapage_attacks(self, guild: discord.Guild, since: datetime):
        channel = self.bot.get_channel(ATTACKS_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return
        # compute incremental counts from messages since
        incr_users = {}
        incr_targets = {}
        async for m in channel.history(limit=1000, after=since):
            # check embed or content for attack pattern: title or starting line "⚔️ Attaque lancée" or similar
            # Accept both embeds and plain messages
            processed = False
            # check embed first
            if m.embeds:
                emb = m.embeds[0]
                title = (emb.title or "")
                if title.startswith("⚔️ Attaque"):
                    # parse fields: coéquipiers and target
                    coops = []
                    target = None
                    for f in emb.fields:
                        if f.name and "Coéquipiers" in f.name:
                            # mentions separated by commas or spaces
                            # extract all <@...> mentions
                            tokens = f.value.replace(",", " ").split()
                            for tok in tokens:
                                if tok.startswith("<@") and tok.endswith(">"):
                                    try:
                                        uid = int(tok.replace("<@!", "").replace("<@", "").replace(">", ""))
                                        coops.append(uid)
                                    except Exception:
                                        continue
                        if f.name and ("Guilde" in f.name or "Alliance" in f.name or "Guilde/Alliance" in f.name):
                            target = f.value.strip()
                    # author + coops are attackers
                    all_attackers = [m.author.id] + coops
                    for uid in all_attackers:
                        incr_users[uid] = incr_users.get(uid, 0) + 1
                    if target:
                        incr_targets[target] = incr_targets.get(target, 0) + 1
                    processed = True
            # fallback: parse plain content
            if not processed and m.content:
                text = m.content
                if "⚔️ Attaque" in text:
                    # try to extract "Coéquipiers :" and "Guilde/Alliance attaquée :"
                    lines = text.splitlines()
                    coops = []
                    target = None
                    for ln in lines:
                        if "Coéquipiers" in ln:
                            # find mentions in the line
                            tokens = ln.replace(",", " ").split()
                            for tok in tokens:
                                if tok.startswith("<@") and tok.endswith(">"):
                                    try:
                                        uid = int(tok.replace("<@!", "").replace("<@", "").replace(">", ""))
                                        coops.append(uid)
                                    except Exception:
                                        continue
                        if "Guilde" in ln and "attaqu" in ln:
                            # take part after colon
                            if ":" in ln:
                                target = ln.split(":", 1)[1].strip()
                            else:
                                # fallback entire line
                                target = ln.strip()
                    all_attackers = [m.author.id] + coops
                    for uid in all_attackers:
                        incr_users[uid] = incr_users.get(uid, 0) + 1
                    if target:
                        incr_targets[target] = incr_targets.get(target, 0) + 1

        # merge with existing totals and seed
        try:
            existing_users = get_attacks_by_user_all(guild.id) or {}
        except Exception:
            existing_users = {}
        try:
            existing_targets = get_attacks_by_target_all(guild.id) or {}
        except Exception:
            existing_targets = {}

        # add increments
        for uid, cnt in incr_users.items():
            existing_users[int(uid)] = int(existing_users.get(int(uid), 0)) + int(cnt)
        for tgt, cnt in incr_targets.items():
            existing_targets[str(tgt)] = int(existing_targets.get(str(tgt), 0)) + int(cnt)

        # seed back
        try:
            seed_attack_user_totals(guild.id, existing_users)
            seed_attack_target_totals(guild.id, existing_targets)
        except Exception:
            pass

    # =============== PUBLIC SAVE ENTRYPOINT (command) ===============
    @app_commands.command(name="snapshot-save", description="Sauvegarder un snapshot des leaderboards et agrégats (manuel).")
    async def snapshot_save(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Commande à utiliser sur un serveur.", ephemeral=True)
            return
        cfg = get_guild_config(guild.id)
        if not cfg:
            await interaction.response.send_message("⚠️ Configuration manquante.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        # run rattrapage since last snapshot
        last = await self._find_last_snapshot_time(guild)
        try:
            await self._rattrapage_defenses(guild, last)
            await self._rattrapage_attacks(guild, last)
        except Exception:
            pass

        payload = await self._gather_snapshot_payload(guild)
        await self._post_snapshot_file(guild, payload)
        await interaction.followup.send("✅ Snapshot envoyé dans le canal dédié.", ephemeral=True)

    # =============== RESTORE (AUTO AU DÉMARRAGE) ===============
    @commands.Cog.listener()
    async def on_ready(self):
        if self._restored_once:
            return
        self._restored_once = True

        # restore once for all guilds
        for guild in self.bot.guilds:
            cfg = get_guild_config(guild.id)
            if not cfg:
                continue
            await self._restore_latest_for_guild(guild, cfg["snapshot_channel_id"])

        # start hourly background task (aligned to hour)
        if self._hourly_task is None:
            self._hourly_task = self.bot.loop.create_task(self._hourly_snapshot_runner())

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

        # 2) Ancien format texte (compat)
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

            seed_aggregates_dynamic(guild.id, global_tot, team_totals, hourly)

            def_tot = {int(k): int(v) for k, v in (latest_payload.get("defense_by_user", {}) or {}).items()}
            ping_tot = {int(k): int(v) for k, v in (latest_payload.get("ping_by_user", {}) or {}).items()}
            wins_tot = {int(k): int(v) for k, v in (latest_payload.get("wins_by_user", {}) or {}).items()}
            loss_tot = {int(k): int(v) for k, v in (latest_payload.get("losses_by_user", {}) or {}).items()}
            seed_leaderboard_totals(guild.id, "defense", def_tot)
            seed_leaderboard_totals(guild.id, "pingeur", ping_tot)
            seed_leaderboard_totals(guild.id, "win", wins_tot)
            seed_leaderboard_totals(guild.id, "loss", loss_tot)

            atk_user = {int(k): int(v) for k, v in (latest_payload.get("attacks_by_user", {}) or {}).items()}
            atk_tgt  = {str(k): int(v) for k, v in (latest_payload.get("attacks_by_target", {}) or {}).items()}
            seed_attack_user_totals(guild.id, atk_user)
            seed_attack_target_totals(guild.id, atk_tgt)
        else:
            clear_baseline(guild.id)

        import cogs.leaderboard as lb
        await lb.update_leaderboards(self.bot, guild)

    # =============== HOURLY RUNNER ===============
    async def _hourly_snapshot_runner(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.now(timezone.utc).astimezone()
            # compute next hour (top of next hour)
            next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            wait_seconds = (next_hour - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            # run snapshot for all guilds
            async with self._running_snapshot:
                for guild in self.bot.guilds:
                    try:
                        last = await self._find_last_snapshot_time(guild)
                        await self._rattrapage_defenses(guild, last)
                        await self._rattrapage_attacks(guild, last)
                        payload = await self._gather_snapshot_payload(guild)
                        await self._post_snapshot_file(guild, payload)
                        import cogs.leaderboard as lb
                        await lb.update_leaderboards(self.bot, guild)
                    except Exception:
                        continue
            # loop continues to wait until next top of hour

async def setup(bot: commands.Bot):
    await bot.add_cog(SnapshotsCog(bot))
