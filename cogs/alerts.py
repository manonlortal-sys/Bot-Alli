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
from .leaderboard import update_leaderboards

# ---------- Constantes ----------
SNAPSHOT_CHANNEL_ID = 1421866144679329984
LOG_FILE = "storage_attack_log.json"
MAX_ATTACKS = 30

# Emojis
EMOJI_VICTORY = "🏆"
EMOJI_DEFEAT = "❌"
EMOJI_INCOMP = "😡"
EMOJI_JOIN = "👍"

ATTACKERS_PREFIX = "⚔️ Attaquants : "

# Anti-spam : 1 alerte / 60s par équipe
last_alerts: dict[tuple[int, int], float] = {}

# ---------- Historique JSON ----------
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
    channel = guild.get_channel(SNAPSHOT_CHANNEL_ID)
    if not channel:
        return

    data = _load_logs()
    logs = data.get(str(guild.id), [])

    if not logs:
        desc = "_Aucune attaque enregistrée._"
    else:
        desc_lines = []
        for log in logs:
            atk = log["attackers"]
            if atk:
                attackers_block = "\n".join(f"    – {a}" for a in atk)
            else:
                attackers_block = "    – (inconnu)"
            desc_lines.append(
                f"• **{log['team']}** attaquée à <t:{log['time']}:t>\n{attackers_block}"
            )
        desc = "\n".join(desc_lines)

    embed = discord.Embed(
        title="📜 Historique des attaques percepteurs",
        description=desc,
        color=discord.Color.gold(),
    )
    embed.set_footer(text=f"Dernières {MAX_ATTACKS} attaques")

    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds:
            await msg.edit(embed=embed)
            return

    await channel.send(embed=embed)


# ---------- Helpers ----------
def _parse_attackers_from_embed(msg: discord.Message) -> List[str]:
    """Lit les lignes d'attaquants déjà dans l'embed."""
    attackers = []
    if not msg.embeds:
        return attackers
    emb = msg.embeds[0]
    for f in emb.fields:
        if f.name == "État du combat":
            for line in f.value.splitlines():
                if line.startswith(ATTACKERS_PREFIX):
                    attackers.append(line[len(ATTACKERS_PREFIX):])
            break
    return attackers


async def build_ping_embed(msg: discord.Message, attackers: Optional[List[str]] = None) -> discord.Embed:
    """Construit l'embed principal, avec multi-attaquants."""
    creator_id = get_message_creator(msg.id)
    creator_member = msg.guild.get_member(creator_id) if creator_id else None

    # défenseurs
    parts = get_participants_detailed(msg.id)
    lines = []
    for user_id, added_by, _ in parts:
        m = msg.guild.get_member(user_id)
        name = m.display_name if m else f"<@{user_id}>"
        if added_by and added_by != user_id:
            addm = msg.guild.get_member(added_by)
            addn = addm.display_name if addm else f"<@{added_by}>"
            lines.append(f"{name} (ajouté par {addn})")
        else:
            lines.append(name)

    defenders_block = "• " + "\n• ".join(lines) if lines else "_Aucun défenseur pour le moment._"

    # résultat via réactions
    reactions = {str(r.emoji): r for r in msg.reactions}
    win = EMOJI_VICTORY in reactions and reactions[EMOJI_VICTORY].count > 0
    loss = EMOJI_DEFEAT in reactions and reactions[EMOJI_DEFEAT].count > 0
    incomplete = EMOJI_INCOMP in reactions and reactions[EMOJI_INCOMP].count > 0

    if win:
        color = discord.Color.green()
        etat = f"{EMOJI_VICTORY} **Défense gagnée**"
    elif loss:
        color = discord.Color.red()
        etat = f"{EMOJI_DEFEAT} **Défense perdue**"
    else:
        color = discord.Color.orange()
        etat = "⏳ **En cours**"

    if incomplete:
        etat += f"\n{EMOJI_INCOMP} Défense incomplète"

    # attaquants
    if attackers is None:
        attackers = _parse_attackers_from_embed(msg)

    if attackers:
        for a in attackers:
            etat += f"\n{ATTACKERS_PREFIX}{a}"

    # nom équipe
    team_id = get_message_team(msg.id)
    team_name = next((t["name"] for t in get_teams(msg.guild.id) if int(t["team_id"]) == int(team_id)), "Percepteur")

    embed = discord.Embed(
        title=f"🛡️ Alerte Attaque {team_name}",
        description="⚠️ **Connectez-vous pour prendre la défense !**",
        color=color,
    )
    if creator_member:
        embed.add_field(name="⚡ Déclenché par", value=creator_member.display_name, inline=False)

    embed.add_field(name="État du combat", value=etat, inline=False)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(name="Défenseurs", value=defenders_block, inline=False)

    embed.set_footer(text="Réagissez : 🏆 gagné • ❌ perdu • 😡 incomplète • 👍 j'ai participé")
    return embed


# ---------- Modal attaquants ----------
class AttackerModal(discord.ui.Modal, title="Ajouter des attaquants"):
    attackers = discord.ui.TextInput(
        label="Noms des attaquants (séparés par des virgules)",
        placeholder="Exemple : VAE, KOBO, AUTRE",
        required=True,
        max_length=200,
    )

    def __init__(self, bot: commands.Bot, msg: discord.Message):
        super().__init__()
        self.bot = bot
        self.msg = msg

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.attackers.value).strip()
        items = [x.strip() for x in raw.split(",") if x.strip()]
        if not items:
            await interaction.response.send_message("Liste vide.", ephemeral=True)
            return

        # maj embed
        current = _parse_attackers_from_embed(self.msg)
        new_list = current + items

        emb = await build_ping_embed(self.msg, new_list)
        await self.msg.edit(embed=emb)

        # maj JSON
        data = _load_logs()
        logs = data.get(str(self.msg.guild.id), [])
        for entry in logs:
            if str(entry.get("message_id")) == str(self.msg.id):
                entry["attackers"] = new_list
                break
        _save_logs(data)

        await update_attack_log_embed(self.bot, self.msg.guild)
        await interaction.response.send_message("Ajout effectué.", ephemeral=True)


# ---------- Views ----------
class AddDefendersSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, message_id: int, claimer_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.message_id = message_id
        self.claimer_id = claimer_id
        self.selected = []

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        min_values=1,
        max_values=3,
        placeholder="Sélectionne jusqu'à 3 défenseurs"
    )
    async def select_users(self, interaction, select):
        self.selected = select.values
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="Confirmer", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, btn):
        await interaction.response.defer(ephemeral=True)
        if not self.selected:
            await interaction.followup.send("Sélection vide.", ephemeral=True)
            return

        channel = interaction.channel
        msg = await channel.fetch_message(self.message_id)

        added_any = False
        for member in self.selected:
            if add_participant(self.message_id, member.id, self.claimer_id, "button"):
                added_any = True
                incr_leaderboard(interaction.guild.id, "defense", member.id)

        if added_any:
            emb = await build_ping_embed(msg)
            await msg.edit(embed=emb)
            await update_leaderboards(self.bot, interaction.guild)

        await interaction.followup.send("Ajout fait.", ephemeral=True)
        self.stop()


class AddDefendersButtonView(discord.ui.View):
    def __init__(self, bot: commands.Bot, message_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.message_id = message_id

    @discord.ui.button(label="Ajouter défenseurs", emoji="🛡️", style=discord.ButtonStyle.primary)
    async def add_def(self, interaction, btn):
        msg = await interaction.channel.fetch_message(self.message_id)

        # n'importe qui ayant mis 👍 peut ajouter
        thumbs = next((r for r in msg.reactions if str(r.emoji) == EMOJI_JOIN), None)
        if not thumbs:
            await interaction.response.send_message("Aucune réaction 👍.", ephemeral=True)
            return

        users = [u async for u in thumbs.users()]
        if interaction.user not in users:
            await interaction.response.send_message("Tu dois mettre 👍 d'abord.", ephemeral=True)
            return

        view = AddDefendersSelectView(self.bot, self.message_id, interaction.user.id)
        await interaction.response.send_message("Sélectionne :", ephemeral=True, view=view)

    @discord.ui.button(label="Attaquant", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def attacker_manual(self, interaction, btn):
        msg = await interaction.channel.fetch_message(self.message_id)
        await interaction.response.send_modal(AttackerModal(self.bot, msg))

    @discord.ui.button(label="Solo", emoji="🧍", style=discord.ButtonStyle.secondary)
    async def delete_msg(self, interaction, btn):
        try:
            msg = await interaction.channel.fetch_message(self.message_id)
            await msg.delete()
            await interaction.response.send_message("Alerte supprimée.", ephemeral=True)
        except:
            await interaction.response.send_message("Erreur.", ephemeral=True)


# ---------- Envoi alerte ----------
async def send_alert(bot, guild, interaction, role_id: int, team_id: int):
    cfg = get_guild_config(guild.id)
    chan = guild.get_channel(cfg["alert_channel_id"]) if cfg else None
    if not chan:
        await interaction.response.send_message("Salon d'alerte introuvable.", ephemeral=True)
        return

    now = time.time()
    key = (guild.id, team_id)
    if key in last_alerts and now - last_alerts[key] < 60:
        await interaction.response.send_message("Alerte déjà envoyée récemment.", ephemeral=True)
        return
    last_alerts[key] = now

    await interaction.response.defer(ephemeral=True)

    msg = await chan.send(f"<@&{role_id}> — **Percepteur attaqué !**")
    upsert_message(
        msg.id, msg.guild.id, msg.channel.id,
        int(msg.created_at.timestamp()),
        creator_id=interaction.user.id,
        team=team_id
    )

    # éviter ping test / prisme
    if team_id not in (0, 8):
        incr_leaderboard(guild.id, "pingeur", interaction.user.id)

    emb = await build_ping_embed(msg)
    await msg.edit(embed=emb, view=AddDefendersButtonView(bot, msg.id))
    await update_leaderboards(bot, guild)

    # JSON historique
    team_name = next((t["name"] for t in get_teams(guild.id) if int(t["team_id"]) == team_id), "Percepteur")
    add_attack_log(guild.id, team_name, int(time.time()), msg.id)
    await update_attack_log_embed(bot, guild)

    # sync avec panneau Attackers
    attackers_cog = bot.get_cog("AttackersCog")
    if attackers_cog:
        await attackers_cog.apply_pending_attacker(msg, interaction.user.id)

    await interaction.followup.send("Alerte envoyée.", ephemeral=True)


# ---------- Ping panel ----------
def make_ping_view(bot: commands.Bot, guild: discord.Guild) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    cfg = get_guild_config(guild.id)
    teams = get_teams(guild.id)

    for t in teams:
        tid = int(t["team_id"])
        if tid == 8:  # prisme -> retiré
            continue

        btn = discord.ui.Button(label=t["label"], style=discord.ButtonStyle.danger)

        async def on_click(inter, role_id=int(t["role_id"]), team_id=int(t["team_id"])):
            await send_alert(bot, guild, inter, role_id, team_id)

        btn.callback = on_click
        view.add_item(btn)

    if cfg and cfg.get("role_test_id"):
        test_btn = discord.ui.Button(label="TEST (Admin)", style=discord.ButtonStyle.secondary)

        async def on_test(inter):
            if cfg.get("admin_role_id") and not any(r.id == cfg["admin_role_id"] for r in inter.user.roles):
                await inter.response.send_message("Réservé admin.", ephemeral=True)
                return
            await send_alert(bot, guild, inter, cfg["role_test_id"], 0)

        test_btn.callback = on_test
        view.add_item(test_btn)

    return view


# ---------- Cog ----------
class AlertsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="pingpanel", description="Publier le panneau d’alerte percepteur")
    async def pingpanel(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Serveur uniquement.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚔️ Ping défenses percepteurs ⚔️",
            description="Clique sur la guilde attaquée pour envoyer une alerte.",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=make_ping_view(self.bot, guild))


async def setup(bot: commands.Bot):
    await bot.add_cog(AlertsCog(bot))
