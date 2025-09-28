from typing import List, Optional
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
)
from .leaderboard import update_leaderboards

# ---------- Emojis ----------
EMOJI_VICTORY = "🏆"
EMOJI_DEFEAT  = "❌"
EMOJI_INCOMP  = "😡"
EMOJI_JOIN    = "👍"

TEAM_NAMES = {
    1: "Wanted",
    2: "Wanted 2",
    3: "Snowflake",
    4: "Secteur K",
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

    # Titre dynamique par guilde
    team = get_message_team(msg.id)
    team_name = TEAM_NAMES.get(team, "Percepteur")
    title = f"🛡️ Alerte Attaque {team_name}"

    embed = discord.Embed(
        title=title,
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

class AddDefendersButtonView(discord.ui.View):
    def __init__(self, bot: commands.Bot, message_id: int):
        super().__init__(timeout=7200)
        self.bot = bot
        self.message_id = message_id

    @discord.ui.button(label="Ajouter défenseurs", style=discord.ButtonStyle.primary, emoji="🛡️", custom_id="add_defenders")
    async def add_defenders(self, interaction: discord.Interaction, button: discord.ui.Button):
        first_id = get_first_defender(self.message_id)
        if first_id is None or interaction.user.id != first_id:
            await interaction.response.send_message("Bouton réservé au premier défenseur (premier 👍).", ephemeral=True)
            return
        await interaction.response.send_message(
            "Sélectionne jusqu'à 3 défenseurs à ajouter :",
            view=AddDefendersSelectView(self.bot, self.message_id, first_id),
            ephemeral=True
        )

# ---------- Panneau de ping ----------
class PingButtonsView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def _handle_click(self, interaction: discord.Interaction, role_id: int, team: int):
        try:
            await interaction.response.defer(ephemeral=True, thinking=False)
        except Exception:
            pass

        guild = interaction.guild
        cfg = get_guild_config(guild.id)
        if not cfg:
            return

        alert_channel = guild.get_channel(cfg["alert_channel_id"])
        if alert_channel is None:
            return

        role_mention = f"<@&{role_id}>"
        content = f"{role_mention} — **Percepteur attaqué !** Merci de vous connecter."
        msg = await alert_channel.send(content)

        upsert_message(
            msg.id,
            msg.guild.id,
            msg.channel.id,
            int(msg.created_at.timestamp()),
            creator_id=interaction.user.id,
            team=team,
        )
        incr_leaderboard(guild.id, "pingeur", interaction.user.id)

        emb = await build_ping_embed(msg)
        # le bouton “Ajouter défenseurs” n'apparaît qu'après le premier 👍 (géré par reactions)
        await msg.edit(embed=emb)
        await update_leaderboards(self.bot, guild)

        try:
            await interaction.followup.send("✅ Alerte envoyée.", ephemeral=True)
        except Exception:
            pass

    # === BOUTONS MIS À JOUR (rouges + 🔔 + MAJUSCULE, WANTED 1) ===
    @discord.ui.button(label="WANTED 1", style=discord.ButtonStyle.danger, emoji="🔔", custom_id="pingpanel:g1")
    async def btn_g1(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        await self._handle_click(interaction, cfg["role_g1_id"], team=1)

    @discord.ui.button(label="WANTED 2", style=discord.ButtonStyle.danger, emoji="🔔", custom_id="pingpanel:g2")
    async def btn_g2(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        await self._handle_click(interaction, cfg["role_g2_id"], team=2)

    @discord.ui.button(label="SNOWFLAKE", style=discord.ButtonStyle.danger, emoji="🔔", custom_id="pingpanel:g3")
    async def btn_g3(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        await self._handle_click(interaction, cfg["role_g3_id"], team=3)

    @discord.ui.button(label="SECTEUR K", style=discord.ButtonStyle.danger, emoji="🔔", custom_id="pingpanel:g4")
    async def btn_g4(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        await self._handle_click(interaction, cfg["role_g4_id"], team=4)

    # TEST reste gris
    @discord.ui.button(label="TEST (Admin)", style=discord.ButtonStyle.secondary, custom_id="pingpanel:test")
    async def btn_test(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        if cfg["admin_role_id"] and not any(r.id == cfg["admin_role_id"] for r in interaction.user.roles):
            await interaction.response.send_message("Bouton réservé aux admins.", ephemeral=True)
            return
        await self._handle_click(interaction, cfg["role_test_id"], team=0)

class AlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pingpanel", description="Publier le panneau d’alerte percepteur")
    async def pingpanel(self, interaction: discord.Interaction):
        title = "⚔️ Ping défenses percepteurs ⚔️"
        desc = (
            "**📢 Clique sur le bouton de la guilde qui se fait attaquer pour générer automatiquement un ping dans le canal défense.**\n\n"
            "*⚠️ Le bouton **TEST** n’est accessible qu’aux administrateurs pour la gestion du bot.*"
        )
        embed = discord.Embed(title=title, description=desc, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=PingButtonsView(self.bot), ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(AlertsCog(bot))
