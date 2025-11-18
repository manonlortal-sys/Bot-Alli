# cogs/alerts.py
from typing import List, Optional
import time, json, os
import discord
from discord.ext import commands
from discord import app_commands

from storage import (
    upsert_message,
    incr_leaderboard,
    get_message_creator,
    get_participants_detailed,
    add_participant,
    get_guild_config,
    get_message_team,
    get_teams,
)
from cogs.leaderboard import update_leaderboards

LOG_FILE = "storage_attack_log.json"
MAX_ATTACKS = 30

EMOJI_VICTORY = "🏆"
EMOJI_DEFEAT = "❌"
EMOJI_INCOMP = "😡"
EMOJI_JOIN = "👍"

ATTACKERS_PREFIX = "⚔️ Attaquants : "
last_alerts: dict[tuple[int, int], float] = {}

# Emojis personnalisés par équipe
TEAM_EMOJIS: dict[int, discord.PartialEmoji] = {
    1: discord.PartialEmoji(name="Wanted", id=1421870161048375357),
    2: discord.PartialEmoji(name="Wanted", id=1421870161048375357),
    3: discord.PartialEmoji(name="Snowflake", id=1421870090588131441),
    4: discord.PartialEmoji(name="SecteurK", id=1421870011902988439),
    5: discord.PartialEmoji(name="Rixe", id=1438158988742230110),
    6: discord.PartialEmoji(name="HagraTime", id=1422120372836503622),
    7: discord.PartialEmoji(name="HagraPasLtime", id=1422120467812323339),
    8: discord.PartialEmoji(name="Prisme", id=1422160491228434503),
    9: discord.PartialEmoji(name="Ruthless", id=1438157046770827304),
}


# ---------------- LOG JSON ----------------

def _load_logs():
    if not os.path.exists(LOG_FILE):
        return {}
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def _save_logs(data):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_attack_log(guild_id: int, team_name: str, timestamp: int, message_id: int):
    data = _load_logs()
    logs = data.get(str(guild_id), [])

    entry = {
        "team": team_name,
        "attackers": [],
        "time": timestamp,
        "message_id": message_id,
    }

    logs.insert(0, entry)
    logs = logs[:MAX_ATTACKS]
    data[str(guild_id)] = logs
    _save_logs(data)
    return logs


async def update_attack_log_embed(bot: commands.Bot, guild: discord.Guild):
    cfg = get_guild_config(guild.id)
    if not cfg:
        return
    channel = guild.get_channel(cfg["snapshot_channel_id"])
    if not channel:
        return

    data = _load_logs()
    logs = data.get(str(guild.id), [])

    if not logs:
        desc = "_Aucune attaque enregistrée._"
    else:
        lines = []
        for log in logs:
            attackers = log.get("attackers") or []
            atk_block = "\n".join(f"    – {a}" for a in attackers) if attackers else "    – (inconnu)"
            lines.append(
                f"• **{log['team']}** attaquée à <t:{log['time']}:t>\n{atk_block}"
            )
        desc = "\n".join(lines)

    embed = discord.Embed(
        title="📜 Historique des attaques percepteurs",
        description=desc,
        color=discord.Color.gold(),
    )

    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds:
            try:
                await msg.edit(embed=embed)
                return
            except:
                break

    await channel.send(embed=embed)


# ---------------- HELPERS ----------------

def _parse_attackers_from_embed(msg: discord.Message) -> List[str]:
    if not msg.embeds:
        return []
    emb = msg.embeds[0]

    attackers = []
    for field in emb.fields:
        if field.name == "État du combat":
            for line in field.value.splitlines():
                s = line.strip()
                if s.startswith(ATTACKERS_PREFIX):
                    attackers.append(s[len(ATTACKERS_PREFIX):])
            break
    return attackers


async def build_ping_embed(msg: discord.Message, attackers: Optional[List[str]] = None) -> discord.Embed:
    creator_id = get_message_creator(msg.id)
    creator_member = msg.guild.get_member(creator_id) if creator_id else None

    parts = get_participants_detailed(msg.id)
    def_lines = []
    for uid, added_by, _ in parts:
        member = msg.guild.get_member(uid)
        name = member.display_name if member else f"<@{uid}>"
        if added_by and added_by != uid:
            by = msg.guild.get_member(added_by)
            bname = by.display_name if by else f"<@{added_by}>"
            def_lines.append(f"{name} (ajouté par {bname})")
        else:
            def_lines.append(name)

    defenders_block = "• " + "\n• ".join(def_lines) if def_lines else "_Aucun défenseur pour le moment._"

    # état combat
    reactions = {str(r.emoji): r for r in msg.reactions}
    win = EMOJI_VICTORY in reactions and reactions[EMOJI_VICTORY].count > 0
    loss = EMOJI_DEFEAT in reactions and reactions[EMOJI_DEFEAT].count > 0
    incomplete = EMOJI_INCOMP in reactions and reactions[EMOJI_INCOMP].count > 0

    if win and not loss:
        color = discord.Color.green()
        etat = f"{EMOJI_VICTORY} **Défense gagnée**"
    elif loss and not win:
        color = discord.Color.red()
        etat = f"{EMOJI_DEFEAT} **Défense perdue**"
    else:
        color = discord.Color.orange()
        etat = "⏳ **En cours**"

    if incomplete:
        etat += f"\n{EMOJI_INCOMP} Défense incomplète"

    if attackers is None:
        attackers = _parse_attackers_from_embed(msg)

    for a in attackers:
        etat += f"\n{ATTACKERS_PREFIX}{a}"

    team_id = get_message_team(msg.id)
    team_name = next(
        (t["name"] for t in get_teams(msg.guild.id) if int(t["team_id"]) == int(team_id)),
        "Percepteur"
    )

    embed = discord.Embed(
        title=f"🛡️ Alerte Attaque {team_name}",
        description="⚠️ **Connectez-vous pour prendre la défense !**",
        color=color,
    )

    if creator_member:
        embed.add_field(name="⚡ Déclenché par", value=creator_member.display_name, inline=False)

    embed.add_field(name="État du combat", value=etat, inline=False)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(name="Défenseurs (👍 ou bouton)", value=defenders_block, inline=False)

    embed.set_footer(text="Réagissez : 🏆 gagné • ❌ perdu • 😡 incomplète • 👍 j'ai participé")

    return embed


# ---------------- MODAL ATTAQUANT ----------------

class AttackerModal(discord.ui.Modal, title="Ajouter des attaquants"):
    attackers = discord.ui.TextInput(
        label="Noms (séparés par virgules)",
        placeholder="VAE, KOBO, HZN...",
        required=True,
        max_length=200,
    )

    def __init__(self, bot: commands.Bot, msg: discord.Message):
        super().__init__(timeout=300)
        self.bot = bot
        self.msg = msg

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.attackers.value).strip()
        items = [x.strip() for x in raw.split(",") if x.strip()]
        if not items:
            await interaction.response.send_message("Liste vide.", ephemeral=True)
            return

        current = _parse_attackers_from_embed(self.msg)
        new_list = current + [a for a in items if a not in current]

        emb = await build_ping_embed(self.msg, attackers=new_list)
        await self.msg.edit(embed=emb)

        data = _load_logs()
        logs = data.get(str(self.msg.guild.id), [])
        for entry in logs:
            if str(entry["message_id"]) == str(self.msg.id):
                entry["attackers"] = new_list
                break
        _save_logs(data)

        await update_attack_log_embed(self.bot, self.msg.guild)
        await interaction.response.send_message("Attaquants ajoutés.", ephemeral=True)


# ---------------- VIEWS ----------------

class AddDefendersSelectView(discord.ui.View):
    def __init__(self, bot, message_id, claimer_id):
        super().__init__(timeout=120)
        self.bot = bot
        self.message_id = message_id
        self.claimer_id = claimer_id
        self.selected = []

    @discord.ui.select(cls=discord.ui.UserSelect, min_values=1, max_values=3)
    async def select_users(self, interaction, select):
        self.selected = select.values
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction, button):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        channel = guild.get_channel(interaction.channel_id) or guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)

        team_id = get_message_team(self.message_id)
        ignore_lb = team_id in (0, 8)

        inserted_any = False
        for member in self.selected:
            ok = add_participant(self.message_id, member.id, self.claimer_id, "button")
            if ok:
                inserted_any = True
                if not ignore_lb:
                    incr_leaderboard(guild.id, "defense", member.id)

        if inserted_any:
            emb = await build_ping_embed(msg)
            await msg.edit(embed=emb)
            if not ignore_lb:
                await update_leaderboards(self.bot, guild)

        await interaction.followup.send("Ajout effectué.", ephemeral=True)
        self.stop()


class AddDefendersButtonView(discord.ui.View):
    def __init__(self, bot, message_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.message_id = message_id

    @discord.ui.button(label="Ajouter défenseurs", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def add_def(self, interaction, button):
        channel = interaction.guild.get_channel(interaction.channel_id) or interaction.guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)

        # ✅ Vérifier qu'il y a des 👍 et que l'utilisateur en fait partie
        thumbs_up = next((r for r in msg.reactions if str(r.emoji) == EMOJI_JOIN), None)
        if not thumbs_up:
            await interaction.response.send_message(
                "Tu dois d’abord réagir avec 👍 sur l’alerte pour ajouter des défenseurs.",
                ephemeral=True
            )
            return

        users = [u async for u in thumbs_up.users()]
        if interaction.user not in users:
            await interaction.response.send_message(
                "Tu dois d’abord réagir avec 👍 sur l’alerte pour ajouter des défenseurs.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Sélectionne jusqu'à 3 défenseurs :",
            view=AddDefendersSelectView(self.bot, self.message_id, interaction.user.id),
            ephemeral=True
        )

    @discord.ui.button(label="Attaquant", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def attacker_manual(self, interaction, button):
        channel = interaction.guild.get_channel(interaction.channel_id) or interaction.guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)
        await interaction.response.send_modal(AttackerModal(self.bot, msg))

    @discord.ui.button(label="Solo", style=discord.ButtonStyle.secondary, emoji="🧍")
    async def delete_alert(self, interaction, button):
        channel = interaction.guild.get_channel(interaction.channel_id) or interaction.guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)
        await msg.delete()
        await interaction.response.send_message("Alerte supprimée.", ephemeral=True)


# ---------------- ENVOI ALERT ----------------

async def send_alert(bot, guild, interaction, role_id: int, team_id: int):
    cfg = get_guild_config(guild.id)
    alert_channel = guild.get_channel(cfg["alert_channel_id"])
    if not alert_channel:
        await interaction.response.send_message("Salon alerte introuvable.", ephemeral=True)
        return

    now = time.time()
    key = (guild.id, team_id)
    if key in last_alerts and now - last_alerts[key] < 60:
        await interaction.response.send_message("Alerte déjà envoyée récemment.", ephemeral=True)
        return
    last_alerts[key] = now

    await interaction.response.defer(ephemeral=True)

    msg = await alert_channel.send(f"<@&{role_id}> — **Percepteur attaqué !**")

    upsert_message(
        msg.id, guild.id, msg.channel.id,
        int(msg.created_at.timestamp()),
        creator_id=interaction.user.id,
        team=team_id,
    )

    # pingeur (sauf test/prisme)
    if team_id not in (0, 8):
        from storage import incr_leaderboard
        incr_leaderboard(guild.id, "pingeur", interaction.user.id)

    emb = await build_ping_embed(msg)
    await msg.edit(embed=emb, view=AddDefendersButtonView(bot, msg.id))

    await update_leaderboards(bot, guild)

    team_name = next(
        (t["name"] for t in get_teams(guild.id) if int(t["team_id"]) == int(team_id)),
        "Percepteur"
    )
    add_attack_log(guild.id, team_name, int(time.time()), msg.id)
    await update_attack_log_embed(bot, guild)

    # 🔥 appliquer alliance stockée AVANT
    atk_cog = bot.get_cog("AttackersCog")
    if atk_cog:
        atk_cog.register_alert_message(interaction.user.id, msg.id)
        await atk_cog.apply_pending_attacker(msg, interaction.user.id)

    await interaction.followup.send("Alerte envoyée.", ephemeral=True)

# ---------------- PANEL ----------------

def make_ping_view(bot: commands.Bot, guild: discord.Guild) -> discord.ui.View:
    view = discord.ui.View(timeout=None)

    cfg = get_guild_config(guild.id)
    teams = get_teams(guild.id)

    for t in teams:
        tid = int(t["team_id"])
        if tid == 8:
            continue

        emoji = TEAM_EMOJIS.get(tid)
        btn = discord.ui.Button(
            label=t["label"],
            style=discord.ButtonStyle.danger,
            emoji=emoji
        )

        async def cb(interaction, role_id=t["role_id"], team_id=tid):
            await send_alert(bot, guild, interaction, role_id, team_id)

        btn.callback = cb
        view.add_item(btn)

    if cfg.get("role_test_id"):
        test_btn = discord.ui.Button(label="TEST", style=discord.ButtonStyle.secondary)

        async def cb2(interaction):
            if cfg.get("admin_role_id") and not any(r.id == cfg["admin_role_id"] for r in interaction.user.roles):
                await interaction.response.send_message("Admin only.", ephemeral=True)
                return
            await send_alert(bot, guild, interaction, cfg["role_test_id"], 0)

        test_btn.callback = cb2
        view.add_item(test_btn)

    return view


# ---------------- COG ----------------

class AlertsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="pingpanel", description="Publier le panneau de ping défense")
    async def pingpanel(self, interaction: discord.Interaction):
        guild = interaction.guild

        embed = discord.Embed(
            title="⚔️ Ping défenses percepteurs",
            description="Clique sur la guilde attaquée pour générer le ping.",
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(embed=embed, view=make_ping_view(self.bot, guild))


async def setup(bot):
    await bot.add_cog(AlertsCog(bot))
