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
EMOJI_DEFEAT = "❌"
EMOJI_INCOMP = "😡"
EMOJI_JOIN = "👍"

# ---------- Cache anti-spam ----------
last_alerts: dict[tuple[int, int], float] = {}

# ---------- Emojis personnalisés par équipe ----------
# team_id -> PartialEmoji
TEAM_EMOJIS: dict[int, discord.PartialEmoji] = {
    1: discord.PartialEmoji(name="Wanted", id=1421870161048375357),
    2: discord.PartialEmoji(name="Wanted", id=1421870161048375357),
    3: discord.PartialEmoji(name="Snowflake", id=1421870090588131441),
    4: discord.PartialEmoji(name="SecteurK", id=1421870011902988439),
    # 5: (LaBande) — supprimé
    6: discord.PartialEmoji(name="HagraTime", id=1422120372836503622),
    7: discord.PartialEmoji(name="HagraPasLtime", id=1422120467812323339),
    # PRISME
    8: discord.PartialEmoji(name="Prisme", id=1422160491228434503),
}

# ---------- Helpers pour les attaquants ----------
ATTACKERS_PREFIX = "⚔️ Attaquants : "

def _parse_attackers_from_embed(msg: discord.Message) -> List[str]:
    attackers: List[str] = []
    if not msg.embeds:
        return attackers
    emb = msg.embeds[0]
    for field in emb.fields:
        if field.name == "État du combat":
            for line in (field.value or "").splitlines():
                line = line.strip()
                if line.startswith(ATTACKERS_PREFIX):
                    attackers.append(line[len(ATTACKERS_PREFIX) :].strip())
            break
    return attackers[:3]


# ---------- Embed constructeur ----------
async def build_ping_embed(msg: discord.Message, attackers: Optional[List[str]] = None) -> discord.Embed:
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
    win = EMOJI_VICTORY in reactions and reactions[EMOJI_VICTORY].count > 0
    loss = EMOJI_DEFEAT in reactions and reactions[EMOJI_DEFEAT].count > 0
    incomplete = EMOJI_INCOMP in reactions and reactions[EMOJI_INCOMP].count > 0

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

    if attackers is None:
        attackers = _parse_attackers_from_embed(msg)
    if attackers:
        for a in attackers[:3]:
            etat += f"\n{ATTACKERS_PREFIX}{a}"

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
    embed.add_field(name="État du combat", value=etat, inline=False)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(name="Défenseurs (👍 ou ajout via bouton)", value=defenders_block, inline=False)
    embed.set_footer(text="Réagissez : 🏆 gagné • ❌ perdu • 😡 incomplète • 👍 j'ai participé")
    return embed


# ---------- Modal Attaquants ----------
class AttackersModal(discord.ui.Modal, title="📝 Attaquants"):
    attackers_text = discord.ui.TextInput(
        label="Alliance/Guilde attaquante",
        placeholder="Ex: [BLA] Black Legion",
        required=True,
        max_length=120,
        style=discord.TextStyle.short,
    )

    def __init__(self, message_id: int):
        super().__init__(timeout=300)
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except Exception:
            pass

        guild = interaction.guild
        channel = guild.get_channel(interaction.channel_id) or guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)

        current = _parse_attackers_from_embed(msg)
        if len(current) >= 3:
            return

        new_entry = str(self.attackers_text).strip()
        if not new_entry:
            return

        updated = current + [new_entry]
        emb = await build_ping_embed(msg, attackers=updated[:3])
        await msg.edit(embed=emb)


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
        channel = interaction.guild.get_channel(interaction.channel_id) or interaction.guild.get_thread(interaction.channel_id)
        msg = await channel.fetch_message(self.message_id)

        thumbs_up = None
        for reaction in msg.reactions:
            if str(reaction.emoji) == "👍":
                thumbs_up = reaction
                break

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

    @discord.ui.button(label="Attaquants", style=discord.ButtonStyle.secondary, emoji="❓", custom_id="add_attackers")
    async def add_attackers(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AttackersModal(self.message_id))

    @discord.ui.button(label="Solo", style=discord.ButtonStyle.danger, emoji="🧍", custom_id="delete_alert")
    async def delete_alert(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            channel = interaction.guild.get_channel(interaction.channel_id) or interaction.guild.get_thread(interaction.channel_id)
            msg = await channel.fetch_message(self.message_id)
            await msg.delete()
            await interaction.response.send_message("✅ Alerte supprimée.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la suppression : {e}", ephemeral=True)


# ---------- Panneau de ping (dynamique) ----------
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

        try:
            await interaction.response.defer(ephemeral=True, thinking=False)
        except Exception:
            pass

        alert_channel = guild.get_channel(cfg["alert_channel_id"]) if cfg else None
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
            team=team_id,
        )
        incr_leaderboard(guild.id, "pingeur", interaction.user.id)

        emb = await build_ping_embed(msg)
        await msg.edit(embed=emb, view=AddDefendersButtonView(bot, msg.id))
        await update_leaderboards(bot, guild)

        try:
            await interaction.followup.send("✅ Alerte envoyée.", ephemeral=True)
        except Exception:
            pass

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

    if cfg and cfg.get("role_test_id"):
        test_btn = discord.ui.Button(
            label="TEST (Admin)", style=discord.ButtonStyle.secondary, custom_id="pingpanel:test"
        )

        async def on_test(interaction: discord.Interaction):
            if cfg["admin_role_id"] and not any(r.id == cfg["admin_role_id"] for r in interaction.user.roles):
                await interaction.response.send_message("Bouton réservé aux admins.", ephemeral=True)
                return
            await handle_click(interaction, cfg["role_test_id"], team_id=0)

        test_btn.callback = on_test  # type: ignore
        view.add_item(test_btn)

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
