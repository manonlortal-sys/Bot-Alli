# cogs/alerts.py
from typing import List, Optional
import time
import discord
from discord.ext import commands
from discord import app_commands

from storage import (
    upsert_message,
    incr_leaderboard,
    get_message_creator,
    get_participants_detailed,
    get_first_defender,
    add_participant,
    get_guild_config,
    get_message_team,
    get_teams,
)
from .leaderboard import update_leaderboards

# ---------- Emojis ----------
EMOJI_VICTORY = "🏆"
EMOJI_DEFEAT  = "❌"
EMOJI_INCOMP  = "😡"
EMOJI_JOIN    = "👍"

# ---------- Cache anti-spam ----------
last_alerts: dict[tuple[int, int], float] = {}

# ---------- Emojis personnalisés par équipe ----------
TEAM_EMOJIS: dict[int, discord.PartialEmoji] = {
    1: discord.PartialEmoji(name="Wanted", id=1421870161048375357),
    2: discord.PartialEmoji(name="Wanted", id=1421870161048375357),
    3: discord.PartialEmoji(name="Snowflake", id=1421870090588131441),
    4: discord.PartialEmoji(name="SecteurK", id=1421870011902988439),
    6: discord.PartialEmoji(name="HagraTime", id=1422120372836503622),
    7: discord.PartialEmoji(name="HagraPasLtime", id=1422120467812323339),
    8: discord.PartialEmoji(name="Prisme", id=1422160491228434503),
}

# ---------- Embed constructeur ----------
async def build_ping_embed(msg: discord.Message) -> discord.Embed:
    creator_id: Optional[int] = get_message_creator(msg.id)
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
    win        = EMOJI_VICTORY in reactions and reactions[EMOJI_VICTORY].count > 0
    loss       = EMOJI_DEFEAT  in reactions and reactions[EMOJI_DEFEAT].count  > 0
    incomplete = EMOJI_INCOMP  in reactions and reactions[EMOJI_INCOMP].count  > 0

    if win and not loss:
        color = discord.Color.green()
        etat = f"{EMOJI_VICTORY} **Défense gagnée**"
        if incomplete:
            etat += f"\n{EMOJI_INCOMP} Défense incomplète"
    elif loss and not win:
        color = discord.Color.red()
        etat = f"{EMOJI_DEFEAT} **Défense perdue**"
        if incomplete:
            etat += f"\n{EMOJI_INCOMP} Défense incomplète"
    else:
        color = discord.Color.orange()
        etat = "⏳ **En cours**"
        if incomplete:
            etat += f"\n{EMOJI_INCOMP} Défense incomplète"

    # Attaquants (stockés dans le footer de l’embed original si présent)
    attackers_line = ""
    if msg.embeds and msg.embeds[0].footer and "Attaquants:" in msg.embeds[0].footer.text:
        attackers_line = msg.embeds[0].footer.text.split("Attaquants:", 1)[1].strip()

    team_id = get_message_team(msg.id)
    team_name = None
    if team_id is not None:
        for t in get_teams(msg.guild.id):
            if int(t["team_id"]) == int(team_id):
                team_name = t["name"]
                break
    if not team_name:
        team_name = "Percepteur"

    embed = discord.Embed(
        title=f"🛡️ Alerte Attaque {team_name}",
        description="⚠️ **Connectez-vous pour prendre la défense !**",
        color=color,
    )
    if creator_member:
        embed.add_field(name="⚡ Déclenché par", value=creator_member.display_name, inline=False)
    if attackers_line:
        etat += f"\n❓ **Attaquants :** {attackers_line}"
    embed.add_field(name="État du combat", value=etat, inline=False)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(name="Défenseurs (👍 ou ajout via bouton)", value=defenders_block, inline=False)
    embed.set_footer(text="Réagissez : 🏆 gagné • ❌ perdu • 😡 incomplète • 👍 j'ai participé")
    return embed

# ---------- Modal pour Attaquants ----------
class AttaquantsModal(discord.ui.Modal, title="⚔️ Attaquants"):
    name = discord.ui.TextInput(
        label="Entre le nom de l’alliance ou de la guilde qui attaque",
        placeholder="Ex: [WANTED], Snowflake, etc.",
        max_length=100,
        required=True,
    )

    def __init__(self, message: discord.Message):
        super().__init__(timeout=120)
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        embed = await build_ping_embed(self.message)
        current_footer = embed.footer.text or ""
        # stocker attaquants dans le footer
        embed.set_footer(text=f"Attaquants: {self.name.value}")
        await self.message.edit(embed=embed)
        await interaction.response.send_message("✅ Attaquants ajoutés.", ephemeral=True)

# ---------- Views (ajout défenseurs) ----------
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
        if interaction.user.id != self.claimer_id:
            await interaction.followup.send("Action réservée au premier défenseur.", ephemeral=True)
            return
        if not self.selected_users:
            await interaction.followup.send("Sélection vide.", ephemeral=True)
            return

        guild = interaction.guild
        channel = guild.get_channel(interaction.channel_id) or guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)

        added_any = False
        for member in self.selected_users:
            from storage import add_participant, incr_leaderboard
            inserted = add_participant(self.message_id, member.id, self.claimer_id, "button")
            if inserted:
                added_any = True
                incr_leaderboard(guild.id, "defense", member.id)

        if added_any:
            emb = await build_ping_embed(msg)
            await msg.edit(embed=emb)
            await update_leaderboards(self.bot, guild)

        await interaction.followup.send("✅ Ajout effectué.", ephemeral=True)
        self.stop()

# ---------- Boutons additionnels ----------
class AddDefendersButtonView(discord.ui.View):
    def __init__(self, bot: commands.Bot, message_id: int):
        super().__init__(timeout=7200)
        self.bot = bot
        self.message_id = message_id

    @discord.ui.button(label="Ajouter défenseurs", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def add_defenders(self, interaction: discord.Interaction, button: discord.ui.Button):
        from storage import get_first_defender
        first_id = get_first_defender(self.message_id)
        if first_id is None or interaction.user.id != first_id:
            await interaction.response.send_message("Bouton réservé au premier défenseur (premier 👍).", ephemeral=True)
            return
        await interaction.response.send_message(
            "Sélectionne jusqu'à 3 défenseurs à ajouter :",
            view=AddDefendersSelectView(self.bot, self.message_id, first_id),
            ephemeral=True
        )

    @discord.ui.button(label="Attaquants", style=discord.ButtonStyle.secondary, emoji="❓")
    async def attaquants(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(interaction.channel_id) or interaction.guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)
        await interaction.response.send_modal(AttaquantsModal(msg))

# ---------- Ping Panel ----------
class PingButtonsView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

def make_ping_view(bot: commands.Bot, guild: discord.Guild) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    cfg = get_guild_config(guild.id)
    teams = get_teams(guild.id)

    async def handle_click(interaction: discord.Interaction, role_id: int, team_id: int):
        now = time.time()
        key = (guild.id, team_id)
        if key in last_alerts and now - last_alerts[key] < 60:
            await interaction.response.send_message("L'alerte a déjà été envoyée par un autre joueur!", ephemeral=True)
            return
        last_alerts[key] = now

        await interaction.response.defer(ephemeral=True, thinking=False)
        alert_channel = guild.get_channel(cfg["alert_channel_id"]) if cfg else None
        if alert_channel is None:
            return

        role_mention = f"<@&{role_id}>"
        content = f"{role_mention} — **Percepteur attaqué !** Merci de vous connecter."
        msg = await alert_channel.send(content)

        upsert_message(
            msg.id, msg.guild.id, msg.channel.id, int(msg.created_at.timestamp()),
            creator_id=interaction.user.id, team=team_id,
        )
        incr_leaderboard(guild.id, "pingeur", interaction.user.id)

        emb = await build_ping_embed(msg)
        await msg.edit(embed=emb, view=AddDefendersButtonView(bot, msg.id))
        await update_leaderboards(bot, guild)
        await interaction.followup.send("✅ Alerte envoyée.", ephemeral=True)

    for t in teams:
        tid = int(t["team_id"])
        emoji = TEAM_EMOJIS.get(tid, "🔔")
        style = discord.ButtonStyle.primary if tid == 8 else discord.ButtonStyle.danger
        btn = discord.ui.Button(
            label=str(t["label"])[:80],
            style=style,
            emoji=emoji,
            custom_id=f"pingpanel:team:{t['team_id']}",
        )
        async def on_click(interaction: discord.Interaction, role_id=int(t["role_id"]), team_id=int(t["team_id"])):
            await handle_click(interaction, role_id, team_id)
        btn.callback = on_click  # type: ignore
        view.add_item(btn)

    return view

class AlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pingpanel", description="Publier le panneau d’alerte percepteur")
    async def pingpanel(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Commande à utiliser sur un serveur.", ephemeral=True)
            return
        title = "⚔️ Ping défenses percepteurs ⚔️"
        desc = (
            "**📢 Clique sur le bouton de la guilde qui se fait attaquer pour générer automatiquement un ping dans le canal défense.**\n\n"
            "*⚠️ Le bouton **TEST** n’est accessible qu’aux administrateurs pour la gestion du bot.*"
        )
        embed = discord.Embed(title=title, description=desc, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=make_ping_view(self.bot, guild), ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(AlertsCog(bot))
