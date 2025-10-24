# cogs/attackers.py
import discord
from discord.ext import commands
from discord import app_commands
import time
import asyncio

from .alerts import build_ping_embed, update_attack_log_embed, get_teams

# =============================
# ⚙️  CONFIGURATION
# =============================

ATTACKER_COOLDOWN = 60          # secondes avant qu'un joueur puisse recliquer sur la même alliance
ATTACKER_EXPIRATION = 120       # durée de vie du clic "en attente" (2 min)
ATTACKER_LIST = ["VAE", "WBC", "BRUT", "KOBO", "HZN", "CLT", "METAA", "AUTRE"]

# =============================
# 🧠  MÉMOIRE TEMPORAIRE
# =============================

# Dernière alerte déclenchée par un joueur (clé = user_id, valeur = message_id)
user_last_alert: dict[int, int] = {}

# Alliance cliquée mais pas encore utilisée (clé = user_id, valeur = (nom_alliance, timestamp))
pending_attackers: dict[int, tuple[str, float]] = {}

# Cooldown (clé = (user_id, nom_alliance), valeur = timestamp dernier clic)
attack_cooldowns: dict[tuple[int, str], float] = {}

# =============================
# 🧩  OUTILS
# =============================

def is_on_cooldown(user_id: int, alliance: str) -> bool:
    key = (user_id, alliance)
    if key not in attack_cooldowns:
        return False
    return (time.time() - attack_cooldowns[key]) < ATTACKER_COOLDOWN

def set_cooldown(user_id: int, alliance: str):
    attack_cooldowns[(user_id, alliance)] = time.time()

def set_pending_attacker(user_id: int, alliance: str):
    pending_attackers[user_id] = (alliance, time.time())

def get_pending_attacker(user_id: int):
    if user_id not in pending_attackers:
        return None
    name, ts = pending_attackers[user_id]
    if time.time() - ts > ATTACKER_EXPIRATION:
        del pending_attackers[user_id]
        return None
    return name

# =============================
# 🧱  PANNEAU D'ATTAQUE
# =============================

def make_attack_view(bot: commands.Bot) -> discord.ui.View:
    view = discord.ui.View(timeout=None)

    for alliance in ATTACKER_LIST:
        btn = discord.ui.Button(label=alliance, style=discord.ButtonStyle.danger)

        async def on_click(interaction: discord.Interaction, alliance_name=alliance):
            user = interaction.user
            user_id = user.id

            # Vérifie le cooldown
            if is_on_cooldown(user_id, alliance_name):
                await interaction.response.send_message(
                    f"⏱️ Tu dois attendre avant de recliquer sur **{alliance_name}** (60 s).",
                    ephemeral=True
                )
                return

            set_cooldown(user_id, alliance_name)

            # Cherche une alerte existante
            guild = interaction.guild
            if user_id in user_last_alert:
                try:
                    msg_id = user_last_alert[user_id]
                    msg = await interaction.channel.fetch_message(msg_id)
                except Exception:
                    msg = None
            else:
                msg = None

            if msg and msg.embeds:
                # Met à jour l'embed existant
                emb = await build_ping_embed(msg, attackers=[alliance_name])
                try:
                    await msg.edit(embed=emb)
                    await interaction.response.send_message(
                        f"✅ Alliance **{alliance_name}** appliquée à ta dernière alerte.",
                        ephemeral=True
                    )
                except discord.HTTPException:
                    await interaction.response.send_message(
                        "⚠️ Erreur lors de la mise à jour de l'alerte.",
                        ephemeral=True
                    )
            else:
                # Sinon, stocke l'alliance pour la prochaine alerte
                set_pending_attacker(user_id, alliance_name)
                await interaction.response.send_message(
                    f"🕒 Alliance **{alliance_name}** enregistrée. Elle sera appliquée à ta prochaine alerte (pendant 2 min).",
                    ephemeral=True
                )

        btn.callback = on_click  # type: ignore
        view.add_item(btn)

    return view

# =============================
# 📢  COG PRINCIPAL
# =============================

class AttackersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- Commande d'envoi du panneau ----
    @app_commands.command(name="attackpanel", description="Publier le panneau des alliances attaquantes")
    async def attackpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📢 ALLIANCE ATTAQUANTE",
            description=(
                "Clique **une seule fois** sur l’alliance qui attaque **avant ou après** avoir cliqué sur la guilde attaquée.\n\n"
                "💡 L’alerte du canal défense se mettra à jour avec cette info !"
            ),
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, view=make_attack_view(self.bot))

    # ---- Liaison automatique avec les alertes créées ----
    # Appelée depuis alerts.py quand une alerte est envoyée
    async def apply_pending_attacker(self, message: discord.Message, user_id: int):
        """Applique une alliance en attente à une alerte nouvellement créée (si existante)."""
        alliance = get_pending_attacker(user_id)
        if not alliance:
            return False

        emb = await build_ping_embed(message, attackers=[alliance])
        try:
            await message.edit(embed=emb)
            del pending_attackers[user_id]
            return True
        except discord.HTTPException:
            return False

# =============================
# 🔧  SETUP
# =============================

async def setup(bot: commands.Bot):
    await bot.add_cog(AttackersCog(bot))
