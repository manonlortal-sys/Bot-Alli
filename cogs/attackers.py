# cogs/attackers.py
import discord
from discord.ext import commands
from discord import app_commands
import time
import json
from typing import Optional, Tuple, List

from .alerts import build_ping_embed, update_attack_log_embed, LOG_FILE

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

def get_pending_attacker(user_id: int) -> Optional[str]:
    if user_id not in pending_attackers:
        return None
    name, ts = pending_attackers[user_id]
    if time.time() - ts > ATTACKER_EXPIRATION:
        del pending_attackers[user_id]
        return None
    return name

# JSON helpers for the same file used by alerts.py (LOG_FILE)
def _load_logs_from_file() -> dict:
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

def _save_logs_to_file(data: dict):
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        # best-effort: don't raise in production flow
        pass

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

            # Cherche une alerte existante (dernière alerte connue pour cet utilisateur)
            msg = None
            try:
                if user_id in user_last_alert:
                    # fetch in the channel where the alert was sent if possible
                    msg_id = user_last_alert[user_id]
                    # we don't know the channel, try search by id in recent channels — best-effort:
                    # attempt to fetch from the interaction channel first
                    try:
                        msg = await interaction.channel.fetch_message(msg_id)
                    except Exception:
                        # fallback: try guild channels where bot can see message
                        for ch in interaction.guild.text_channels:
                            try:
                                msg = await ch.fetch_message(msg_id)
                                if msg:
                                    break
                            except Exception:
                                continue
            except Exception:
                msg = None

            if msg and msg.embeds:
                # Met à jour l'embed existant en ajoutant l'alliance
                emb = await build_ping_embed(msg, attackers=[alliance_name])
                try:
                    await msg.edit(embed=emb)
                except discord.HTTPException:
                    await interaction.response.send_message(
                        "⚠️ Erreur lors de la mise à jour de l'alerte.",
                        ephemeral=True
                    )
                    return

                # --- NOUVEAU : écrire l'alliance dans le fichier d'historique ---
                # extraire la guilde attaquée depuis le titre
                attacked = None
                try:
                    title = msg.embeds[0].title or ""
                    prefix = "🛡️ Alerte Attaque "
                    if title.startswith(prefix):
                        attacked = title.replace(prefix, "").strip()
                except Exception:
                    attacked = None

                if attacked:
                    data = _load_logs_from_file()
                    logs = data.get(str(interaction.guild.id), [])
                    # trouver la première entrée correspondante non encore remplie (attackers == "—")
                    for entry in logs:
                        if entry.get("team", "").lower() == attacked.lower() and entry.get("attackers", "—") == "—":
                            entry["attackers"] = alliance_name
                            break
                    data[str(interaction.guild.id)] = logs[:30]
                    _save_logs_to_file(data)
                    # rafraîchir l'embed d'historique
                    try:
                        await update_attack_log_embed(interaction.guild)
                    except Exception:
                        # best-effort
                        pass

                await interaction.response.send_message(
                    f"✅ Alliance **{alliance_name}** appliquée à ta dernière alerte.",
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
    async def apply_pending_attacker(self, message: discord.Message, user_id: int) -> bool:
        """Applique une alliance en attente à une alerte nouvellement créée (si existante).
           Si appliquée, écrit l'alliance dans le fichier d'historique et met à jour l'embed d'historique.
        """
        alliance = get_pending_attacker(user_id)
        if not alliance:
            return False

        emb = await build_ping_embed(message, attackers=[alliance])
        try:
            await message.edit(embed=emb)
        except discord.HTTPException:
            return False

        # --- NOUVEAU : écrire l'alliance dans le fichier d'historique ---
        attacked = None
        try:
            title = message.embeds[0].title or ""
            prefix = "🛡️ Alerte Attaque "
            if title.startswith(prefix):
                attacked = title.replace(prefix, "").strip()
        except Exception:
            attacked = None

        if attacked:
            data = _load_logs_from_file()
            logs = data.get(str(message.guild.id), [])
            # trouver la première entrée correspondante non encore remplie (attackers == "—")
            for entry in logs:
                if entry.get("team", "").lower() == attacked.lower() and entry.get("attackers", "—") == "—":
                    entry["attackers"] = alliance
                    break
            data[str(message.guild.id)] = logs[:30]
            _save_logs_to_file(data)
            try:
                await update_attack_log_embed(message.guild)
            except Exception:
                pass

        # supprimer le jeton en attente
        if user_id in pending_attackers:
            del pending_attackers[user_id]
        return True

# =============================
# 🔧  SETUP
# =============================

async def setup(bot: commands.Bot):
    await bot.add_cog(AttackersCog(bot))
