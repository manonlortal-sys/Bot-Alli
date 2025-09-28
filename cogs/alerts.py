# cogs/alerts.py
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
    get_guild_config,   # lecture de la config serveur (ids canaux & rôles)
)
from .leaderboard import update_leaderboards

# ---------- Emojis exportés (utilisés par reactions.py) ----------
EMOJI_VICTORY = "🏆"
EMOJI_DEFEAT  = "❌"
EMOJI_INCOMP  = "😡"
EMOJI_JOIN    = "👍"

# ---------- Embed constructeur ----------
async def build_ping_embed(
    msg: discord.Message,
    title_override: Optional[str] = None,  # permet d’imposer "Alerte Attaque <GUILDE>"
) -> discord.Embed:
    creator_id: Optional[int] = get_message_creator(msg.id)
    creator_member = msg.guild.get_member(creator_id) if creator_id else None

    parts = get_participants_detailed(msg.id)  # [(user_id, added_by, ts)]
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

    # L’état (gagné/perdu/incomplète) est piloté par reactions.py via DB,
    # ici on reste neutre pour éviter de casser la logique existante.
    etat = "⏳ **En cours**"

    embed = discord.Embed(
        title=(title_override or "🛡️ Alerte Attaque"),
        description="⚠️ **Connectez-vous pour prendre la défense !**",
        color=discord.Color.orange(),
    )
    if creator_member:
        embed.add_field(name="⚡ Déclenché par", value=creator_member.display_name, inline=False)
    embed.add_field(name="État du combat", value=etat, inline=False)
    embed.add_field(name="\u200b", value="\u200b", inline=False)  # séparation visuelle
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

        if interaction.user.id != self.claimer_id:
            await interaction.followup.send("Action réservée au premier défenseur.", ephemeral=True)
            return

        if not self.selected_users:
            await interaction.followup.send("Sélection vide.", ephemeral=True)
            return

        guild = interaction.guild
        channel = guild.get_channel(interaction.channel_id) or guild.get_thread(interaction.channel_id)
        if channel is None:
            await interaction.followup.send("Impossible de retrouver le message d'alerte.", ephemeral=True)
            return

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
            except Exception:
                pass
            try:
                await update_leaderboards(self.bot, guild)
            except Exception:
                pass

        await interaction.followup.send("✅ Ajout effectué.", ephemeral=True)
        self.stop()

class AddDefendersButtonView(discord.ui.View):
    def __init__(self, bot: commands.Bot, message_id: int):
        super().__init__(timeout=7200)  # 2h
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

class PingButtonsView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)  # persistante
        self.bot = bot

    async def _handle_click(self, interaction: discord.Interaction, role_id: int, team: int, guild_name: str):
        # On “defer” tout de suite pour éviter l’erreur 10062 si Discord tarde
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        guild = interaction.guild
        cfg = get_guild_config(guild.id)
        if not cfg:
            await interaction.followup.send("⚠️ Configuration manquante pour ce serveur.", ephemeral=True)
            return

        alert_channel = guild.get_channel(cfg["alert_channel_id"]) or guild.get_thread(cfg["alert_channel_id"])
        if alert_channel is None:
            await interaction.followup.send("⚠️ Canal d’alertes introuvable.", ephemeral=True)
            return

        content = f"<@&{role_id}> — **Percepteur attaqué !** Merci de vous connecter."
        msg = await alert_channel.send(content)

        # Enregistrement DB
        upsert_message(
            msg.id,
            msg.guild.id,
            msg.channel.id,
            int(msg.created_at.timestamp()),
            creator_id=interaction.user.id,
            team=team,  # 1..4 (Wanted1, Wanted2, Snowflake, Secteur K)
        )
        # pingeur++
        try:
            incr_leaderboard(guild.id, "pingeur", interaction.user.id)
        except Exception:
            pass

        # Embed avec titre “Alerte Attaque <GUILDE>”
        emb = await build_ping_embed(msg, title_override=f"🔔 Alerte Attaque {guild_name}")
        try:
            await msg.edit(embed=emb)
        except Exception:
            pass

        # MAJ leaderboards
        try:
            await update_leaderboards(self.bot, guild)
        except Exception:
            pass

        try:
            await interaction.followup.send("✅ Alerte envoyée.", ephemeral=True)
        except Exception:
            pass

    # 4 boutons rouges (danger), libellés MAJUSCULE + 🔔
    @discord.ui.button(label="WANTED 1", style=discord.ButtonStyle.danger, emoji="🔔", custom_id="pingpanel:g1")
    async def btn_wanted1(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        await self._handle_click(interaction, cfg["role_g1_id"], team=1, guild_name="WANTED 1")

    @discord.ui.button(label="WANTED 2", style=discord.ButtonStyle.danger, emoji="🔔", custom_id="pingpanel:g2")
    async def btn_wanted2(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        await self._handle_click(interaction, cfg["role_g2_id"], team=2, guild_name="WANTED 2")

    @discord.ui.button(label="SNOWFLAKE", style=discord.ButtonStyle.danger, emoji="🔔", custom_id="pingpanel:g3")
    async def btn_snowflake(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        await self._handle_click(interaction, cfg["role_g3_id"], team=3, guild_name="SNOWFLAKE")

    @discord.ui.button(label="SECTEUR K", style=discord.ButtonStyle.danger, emoji="🔔", custom_id="pingpanel:g4")
    async def btn_secteurk(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        await self._handle_click(interaction, cfg["role_g4_id"], team=4, guild_name="SECTEUR K")

    # Bouton TEST gris (secondary)
    @discord.ui.button(label="TEST (Admin)", style=discord.ButtonStyle.secondary, custom_id="pingpanel:test")
    async def btn_test(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.guild.id)
        if cfg.get("admin_role_id") and not any(r.id == cfg["admin_role_id"] for r in interaction.user.roles):
            await interaction.response.send_message("Bouton réservé aux admins.", ephemeral=True)
            return
        await self._handle_click(interaction, cfg["role_test_id"], team=0, guild_name="TEST")

class AlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pingpanel", description="Publier le panneau d’alerte percepteur")
    async def pingpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚔️ Ping défenses percepteurs ⚔️",
            description=(
                "**📢 Clique sur la guilde attaquée pour générer automatiquement un ping dans le canal défense.**\n\n"
                "*⚠️ Le bouton **TEST** n’est accessible qu’aux administrateurs pour la gestion du bot.*"
            ),
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=PingButtonsView(self.bot), ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(AlertsCog(bot))
