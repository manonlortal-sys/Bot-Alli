# cogs/attackers.py
import discord
from discord.ext import commands
from discord import app_commands
import time
import json
from typing import Optional, Tuple, List

from .alerts import build_ping_embed, update_attack_log_embed, LOG_FILE

# =============================
# ⚙️ CONFIGURATION
# =============================

ATTACKER_COOLDOWN = 60          # secondes avant qu'un joueur puisse recliquer sur la même alliance
ATTACKER_EXPIRATION = 120       # durée de vie du clic "en attente" (2 min)
ATTACKER_LIST = ["VAE", "WBC", "BRUT", "KOBO", "HZN", "CLT", "AUTRE"]

# =============================
# 🧠 MÉMOIRE TEMPORAIRE
# =============================

user_last_alert: dict[int, int] = {}                      # user_id -> message_id
pending_attackers: dict[int, tuple[str, float]] = {}      # user_id -> (nom_alliance, timestamp)
attack_cooldowns: dict[tuple[int, str], float] = {}       # (user_id, alliance) -> timestamp

# =============================
# 🔧 UTILITAIRES
# =============================

def is_on_cooldown(user_id: int, alliance: str) -> bool:
    key = (user_id, alliance)
    return key in attack_cooldowns and (time.time() - attack_cooldowns[key]) < ATTACKER_COOLDOWN

def set_cooldown(user_id: int, alliance: str):
    attack_cooldowns[(user_id, alliance)] = time.time()

def set_pending_attacker(user_id: int, alliance: str):
    pending_attackers[user_id] = (alliance, time.time())

def get_pending_attacker(user_id: int) -> Optional[str]:
    if user_id not in pending_attackers:
        return None
    name, ts = pending_attackers[user_id]
    if time.time() - ts > ATTACKER_EXPIRATION:
        del pending_attackers[user_id]
        return None
    return name

def _load_logs() -> dict:
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_logs(data: dict):
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# =============================
# 🧩 MISE À JOUR DU JSON
# =============================

def update_attack_log_entry(guild_id: int, message_id: int, alliance_name: str):
    """Met à jour l'entrée correspondante à ce message_id dans le JSON."""
    data = _load_logs()
    logs = data.get(str(guild_id), [])
    for entry in logs:
        if str(entry.get("message_id", "")) == str(message_id):
            entry["attackers"] = alliance_name
            break
    data[str(guild_id)] = logs[:30]
    _save_logs(data)

# =============================
# 🧱 PANNEAU DES ALLIANCES
# =============================

def make_attack_view(bot: commands.Bot) -> discord.ui.View:
    view = discord.ui.View(timeout=None)

    for alliance in ATTACKER_LIST:
        btn = discord.ui.Button(label=alliance, style=discord.ButtonStyle.danger)

        async def on_click(interaction: discord.Interaction, alliance_name=alliance):
            await interaction.response.defer(ephemeral=True, thinking=False)
            user = interaction.user
            user_id = user.id

            # Vérifie cooldown
            if is_on_cooldown(user_id, alliance_name):
                await interaction.followup.send(
                    f"⏱️ Tu dois attendre avant de recliquer sur **{alliance_name}** (60 s).",
                    ephemeral=True
                )
                return
            set_cooldown(user_id, alliance_name)

            msg = None
            if user_id in user_last_alert:
                msg_id = user_last_alert[user_id]
                # Cherche dans le salon courant puis dans les salons visibles
                try:
                    msg = await interaction.channel.fetch_message(msg_id)
                except Exception:
                    for ch in interaction.guild.text_channels:
                        try:
                            msg = await ch.fetch_message(msg_id)
                            if msg:
                                break
                        except Exception:
                            continue

            # ✅ Si une alerte existe déjà pour ce joueur
            if msg and msg.embeds:
                emb = await build_ping_embed(msg, attackers=[alliance_name])
                try:
                    await msg.edit(embed=emb)
                except discord.HTTPException:
                    await interaction.followup.send("⚠️ Erreur lors de la mise à jour de l'alerte.", ephemeral=True)
                    return

                # 🔄 Met à jour le JSON + embed historique
                try:
                    update_attack_log_entry(interaction.guild.id, msg.id, alliance_name)
                    await update_attack_log_embed(bot, interaction.guild)
                except Exception:
                    pass

                await interaction.followup.send(
                    f"✅ Alliance **{alliance_name}** appliquée à ta dernière alerte.",
                    ephemeral=True
                )

            # ⏳ Sinon, enregistre pour la prochaine alerte
            else:
                set_pending_attacker(user_id, alliance_name)
                await interaction.followup.send(
                    f"🕒 Alliance **{alliance_name}** enregistrée. Elle sera appliquée à ta prochaine alerte (pendant 2 min).",
                    ephemeral=True
                )

        btn.callback = on_click  # type: ignore
        view.add_item(btn)

    return view

# =============================
# ⚔️  COG PRINCIPAL
# =============================

class AttackersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---- Commande d’envoi du panneau ----
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

    # ---- Applique une alliance en attente à une alerte nouvellement créée ----
    async def apply_pending_attacker(self, message: discord.Message, user_id: int) -> bool:
        alliance = get_pending_attacker(user_id)
        if not alliance:
            return False

        emb = await build_ping_embed(message, attackers=[alliance])
        try:
            await message.edit(embed=emb)
        except discord.HTTPException:
            return False

        try:
            update_attack_log_entry(message.guild.id, message.id, alliance)
            await update_attack_log_embed(self.bot, message.guild)
        except Exception:
            pass

        if user_id in pending_attackers:
            del pending_attackers[user_id]
        return True

# =============================
# 🔧 SETUP
# =============================

async def setup(bot: commands.Bot):
    await bot.add_cog(AttackersCog(bot))
