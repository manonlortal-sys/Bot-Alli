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
SNAPSHOT_CHANNEL_ID = 1421866144679329984  # canal de suivi (historique)
LOG_FILE = "storage_attack_log.json"
MAX_ATTACKS = 30  # nombre maximum d'entrées affichées dans l'historique

# Emojis
EMOJI_VICTORY = "🏆"
EMOJI_DEFEAT = "❌"
EMOJI_INCOMP = "😡"
EMOJI_JOIN = "👍"

# Emojis personnalisés par équipe
TEAM_EMOJIS: dict[int, discord.PartialEmoji] = {
1: discord.PartialEmoji(name="Wanted", id=1421870161048375357),
2: discord.PartialEmoji(name="Wanted", id=1421870161048375357),
3: discord.PartialEmoji(name="Snowflake", id=1421870090588131441),
4: discord.PartialEmoji(name="SecteurK", id=1421870011902988439),
5: discord.PartialEmoji(name="Rixe", id=1438157003162648656),          # 🆕 RIXE
6: discord.PartialEmoji(name="HagraTime", id=1422120372836503622),
7: discord.PartialEmoji(name="HagraPasLtime", id=1422120467812323339),
8: discord.PartialEmoji(name="Prisme", id=1422160491228434503),
9: discord.PartialEmoji(name="Ruthless", id=1438157046770827304),       # 🆕 RUTHLESS
}

ATTACKERS_PREFIX = "⚔️ Attaquants : "

# Anti-spam : 1 alerte / 60s par équipe (clé = (guild_id, team_id))
last_alerts: dict[tuple[int, int], float] = {}

# ---------- Historique local (30 dernières attaques) ----------
def _load_logs():
    if not os.path.exists(LOG_FILE):
        return {}
    with open(LOG_FILE, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def _save_logs(data):
    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)

# 🆕 Ajout du message_id ici
def add_attack_log(guild_id: int, team_name: str, timestamp: int, message_id: int):
    data = _load_logs()
    logs = data.get(str(guild_id), [])
    entry = {
        "team": team_name,
        "attackers": "—",
        "time": timestamp,
        "message_id": message_id,  # 🆕 Identifiant du message d’alerte
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
        desc = "\n".join(
            f"• **{log['team']}** attaquée à <t:{log['time']}:t> par `{log.get('attackers', '—')}`"
            for log in logs
        )

    embed = discord.Embed(
        title="📜 Historique des attaques percepteurs",
        description=desc,
        color=discord.Color.gold(),
    )
    embed.set_footer(text=f"Dernières {MAX_ATTACKS} attaques")

    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds:
            try:
                await msg.edit(embed=embed)
                return
            except discord.HTTPException:
                break
    await channel.send(embed=embed)

# ---------- Helpers ----------
def _parse_attackers_from_embed(msg: discord.Message) -> List[str]:
    attackers: List[str] = []
    if not msg.embeds:
        return attackers
    emb = msg.embeds[0]
    for field in emb.fields:
        if field.name == "État du combat":
            for line in (field.value or "").splitlines():
                s = line.strip()
                if s.startswith(ATTACKERS_PREFIX):
                    attackers.append(s[len(ATTACKERS_PREFIX):])
            break
    return attackers[:3]

async def build_ping_embed(msg: discord.Message, attackers: Optional[List[str]] = None) -> discord.Embed:
    creator_id = get_message_creator(msg.id)
    creator_member = msg.guild.get_member(creator_id) if creator_id else None

    parts = get_participants_detailed(msg.id)
    lines: List[str] = []
    for user_id, added_by, _ in parts:
        member = msg.guild.get_member(user_id)
        name = member.display_name if member else f"<@{user_id}>"
        if added_by and added_by != user_id:
            bym = msg.guild.get_member(added_by)
            byname = bym.display_name if bym else f"<@{added_by}>"
            lines.append(f"{name} (ajouté par {byname})")
        else:
            lines.append(name)
    defenders_block = "• " + "\n• ".join(lines) if lines else "_Aucun défenseur pour le moment._"

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
    if attackers:
        for a in attackers[:3]:
            etat += f"\n{ATTACKERS_PREFIX}{a}"

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
    embed.add_field(name="Défenseurs (👍 ou ajout via bouton)", value=defenders_block, inline=False)
    embed.set_footer(text="Réagissez : 🏆 gagné • ❌ perdu • 😡 incomplète • 👍 j'ai participé")
    return embed

# ---------- Views ----------
class AddDefendersSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, message_id: int, claimer_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.message_id = message_id
        self.claimer_id = claimer_id
        self.selected_users: List[discord.Member] = []

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        min_values=1,
        max_values=3,
        placeholder="Sélectionne jusqu'à 3 défenseurs",
    )
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_users = select.values
        await interaction.response.defer(ephemeral=True)

    @discord.ui.button(label="Confirmer l'ajout", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not self.selected_users:
            await interaction.followup.send("Sélection vide.", ephemeral=True)
            return

        guild = interaction.guild
        channel = guild.get_channel(interaction.channel_id) or guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)

        added_any = False
        for member in self.selected_users:
            inserted = add_participant(self.message_id, member.id, self.claimer_id, "button")
            if inserted:
                added_any = True
                incr_leaderboard(guild.id, "defense", member.id)

        if added_any:
            emb = await build_ping_embed(msg)
            try:
                await msg.edit(embed=emb)
            except discord.HTTPException:
                pass
            await update_leaderboards(self.bot, guild)

        await interaction.followup.send("✅ Ajout effectué.", ephemeral=True)
        self.stop()

class AddDefendersButtonView(discord.ui.View):
    def __init__(self, bot: commands.Bot, message_id: int):
        super().__init__(timeout=7200)
        self.bot = bot
        self.message_id = message_id

    @discord.ui.button(label="Ajouter défenseurs", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def add_defenders(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(interaction.channel_id) or interaction.guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)

        thumbs_up = next((r for r in msg.reactions if str(r.emoji) == "👍"), None)
        if not thumbs_up:
            await interaction.response.send_message("Aucune réaction 👍 détectée sur ce message.", ephemeral=True)
            return

        users = [u async for u in thumbs_up.users()]
        if interaction.user not in users:
            await interaction.response.send_message("Tu dois réagir avec 👍 avant d’ajouter des défenseurs.", ephemeral=True)
            return

        await interaction.response.send_message(
            "Sélectionne jusqu'à 3 défenseurs à ajouter :",
            view=AddDefendersSelectView(self.bot, self.message_id, interaction.user.id),
            ephemeral=True,
        )

    @discord.ui.button(label="Solo", style=discord.ButtonStyle.danger, emoji="🧍")
    async def delete_alert(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel = interaction.guild.get_channel(interaction.channel_id) or interaction.guild.get_thread(interaction.channel_id)
            msg = await channel.fetch_message(self.message_id)
            await msg.delete()
            await interaction.response.send_message("✅ Alerte supprimée.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la suppression : {e}", ephemeral=True)

# ---------- Envoi alerte ----------
async def send_alert(bot, guild, interaction, role_id: int, team_id: int):
    cfg = get_guild_config(guild.id)
    alert_channel = guild.get_channel(cfg["alert_channel_id"]) if cfg else None
    if not alert_channel:
        await interaction.response.send_message("⚠️ Salon d’alerte introuvable.", ephemeral=True)
        return

    now = time.time()
    key = (guild.id, team_id)
    if key in last_alerts and now - last_alerts[key] < 60:
        await interaction.response.send_message("🚫 Une alerte pour cette équipe a déjà été envoyée récemment.", ephemeral=True)
        return
    last_alerts[key] = now

    await interaction.response.defer(ephemeral=True, thinking=False)

    role_mention = f"<@&{role_id}>"
    content = f"{role_mention} — **Percepteur attaqué !** Merci de vous connecter."
    msg = await alert_channel.send(content)

    upsert_message(
        msg.id,
        msg.guild.id,
        msg.channel.id,
        int(msg.created_at.timestamp()),
        creator_id=interaction.user.id,
        team=team_id,
    )
    incr_leaderboard(guild.id, "pingeur", interaction.user.id)

    emb = await build_ping_embed(msg)
    await msg.edit(embed=emb, view=AddDefendersButtonView(bot, msg.id))
    await update_leaderboards(bot, guild)

    # Historique 🆕 (ajout du message_id ici)
    add_attack_log(
        guild.id,
        next((t["name"] for t in get_teams(guild.id) if int(t["team_id"]) == int(team_id)), "Percepteur"),
        int(time.time()),
        msg.id,  # 🆕 identifiant du message d’alerte
    )
    await update_attack_log_embed(bot, guild)

    # 🔗 Alliance en attente (cog Attackers)
    attackers_cog = bot.get_cog("AttackersCog")
    if attackers_cog:
        await attackers_cog.apply_pending_attacker(msg, interaction.user.id)

    await interaction.followup.send("✅ Alerte envoyée.", ephemeral=True)

# ---------- Panneau principal ----------
def make_ping_view(bot: commands.Bot, guild: discord.Guild) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    cfg = get_guild_config(guild.id)
    teams = get_teams(guild.id)

    for t in teams:
        tid = int(t["team_id"])
        emoji = TEAM_EMOJIS.get(tid, "🔔")
        style = discord.ButtonStyle.primary if tid == 8 else discord.ButtonStyle.danger

        btn = discord.ui.Button(label=str(t["label"])[:80], style=style, emoji=emoji)

        async def on_click(interaction: discord.Interaction, role_id=int(t["role_id"]), team_id=int(t["team_id"])):
            await send_alert(bot, guild, interaction, role_id, team_id)

        btn.callback = on_click  # type: ignore
        view.add_item(btn)

    if cfg and cfg.get("role_test_id"):
        test_btn = discord.ui.Button(label="TEST (Admin)", style=discord.ButtonStyle.secondary)

        async def on_test(interaction: discord.Interaction):
            if cfg.get("admin_role_id") and not any(r.id == cfg["admin_role_id"] for r in interaction.user.roles):
                await interaction.response.send_message("Bouton réservé aux admins.", ephemeral=True)
                return
            await send_alert(bot, guild, interaction, cfg["role_test_id"], team_id=0)

        test_btn.callback = on_test  # type: ignore
        view.add_item(test_btn)

    return view

# ---------- Cog ----------
class AlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pingpanel", description="Publier le panneau d’alerte percepteur")
    async def pingpanel(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Commande à utiliser sur un serveur.", ephemeral=True)
            return

        title = "⚔️ Ping défenses percepteurs ⚔️"
        desc = (
            "**📢 Clique sur le bouton de la guilde qui se fait attaquer pour générer automatiquement un ping dans le canal défense.**\n\n"
            "*⚠️ Le bouton **TEST** n’est accessible qu’aux administrateurs pour la gestion du bot.*"
        )
        embed = discord.Embed(title=title, description=desc, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=make_ping_view(self.bot, guild))

async def setup(bot: commands.Bot):
    await bot.add_cog(AlertsCog(bot))
