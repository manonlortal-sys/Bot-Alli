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

ATTACKER_COOLDOWN = 60          
ATTACKER_EXPIRATION = 120       
ATTACKER_LIST = ["VAE", "WBC", "BRUT", "KOBO", "HZN", "CLT", "AUTRE"]

# =============================
# 🧠 MÉMOIRE TEMPORAIRE
# =============================

user_last_alert: dict[int, int] = {}
pending_attackers: dict[int, tuple[str, float]] = {}
attack_cooldowns: dict[tuple[int, str], float] = {}

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
    data = _load_logs()
    logs = data.get(str(guild_id), [])
    for entry in logs:
        if str(entry.get("message_id")) == str(message_id):
            entry["attackers"] = alliance_name
            break
    data[str(guild_id)] = logs[:30]
    _save_logs(data)

# =============================
# 🔘 BOUTON PERSONNALISÉ (Fix)
# =============================

class AttackButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot, alliance_name: str):
        super().__init__(
            label=alliance_name,
            style=discord.ButtonStyle.danger,
            custom_id=f"attacker_{alliance_name}"
        )
        self.bot = bot
        self.alliance_name = alliance_name

    async def callback(self, interaction: discord.Interaction):
        alliance = self.alliance_name
        user = interaction.user
        user_id = user.id

        await interaction.response.defer(ephemeral=True)

        # Cooldown
        if is_on_cooldown(user_id, alliance):
            await interaction.followup.send(
                f"⏱️ Tu dois attendre avant de recliquer sur **{alliance}**.",
                ephemeral=True
            )
            return
        set_cooldown(user_id, alliance)

        # Retrouver l’alerte précédente si elle existe
        msg = None
        if user_id in user_last_alert:
            msg_id = user_last_alert[user_id]
            try:
                msg = await interaction.channel.fetch_message(msg_id)
            except Exception:
                for ch in interaction.guild.text_channels:
                    try:
                        msg = await ch.fetch_message(msg_id)
                        break
                    except Exception:
                        continue

        # 🔄 Mise à jour immédiate
        if msg and msg.embeds:
            emb = await build_ping_embed(msg, attackers=[alliance])
            try:
                await msg.edit(embed=emb)
            except discord.HTTPException:
                await interaction.followup.send("⚠️ Erreur lors de la mise à jour.", ephemeral=True)
                return

            update_attack_log_entry(interaction.guild.id, msg.id, alliance)
            await update_attack_log_embed(self.bot, interaction.guild)

            await interaction.followup.send(
                f"✅ Alliance **{alliance}** appliquée à ta dernière alerte.",
                ephemeral=True
            )

        # ⏳ En attente pour la prochaine alerte
        else:
            set_pending_attacker(user_id, alliance)
            await interaction.followup.send(
                f"🕒 Alliance **{alliance}** enregistrée.\n"
                "Elle sera appliquée automatiquement à ta **prochaine alerte** (pendant 2 minutes).",
                ephemeral=True
            )


# =============================
# 🧱 FABRICATION DU PANNEAU
# =============================

def make_attack_view(bot: commands.Bot) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for alliance in ATTACKER_LIST:
        view.add_item(AttackButton(bot, alliance))
    return view

# =============================
# ⚔️  COG PRINCIPAL
# =============================

class AttackersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="attackpanel", description="Publier le panneau des alliances attaquantes")
    async def attackpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📢 ALLIANCE ATTAQUANTE",
            description=(
                "Clique **une seule fois** sur l’alliance qui attaque **avant ou après** avoir cliqué sur la guilde attaquée.\n\n"
                "💡 L’alerte du canal défense se mettra automatiquement à jour."
            ),
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, view=make_attack_view(self.bot))

    async def apply_pending_attacker(self, message: discord.Message, user_id: int) -> bool:
        alliance = get_pending_attacker(user_id)
        if not alliance:
            return False

        emb = await build_ping_embed(message, attackers=[alliance])
        try:
            await message.edit(embed=emb)
        except discord.HTTPException:
            return False

        update_attack_log_entry(message.guild.id, message.id, alliance)
        await update_attack_log_embed(self.bot, message.guild)

        if user_id in pending_attackers:
            del pending_attackers[user_id]
        return True


async def setup(bot: commands.Bot):
    await bot.add_cog(AttackersCog(bot))
