# cogs/attackers.py
import discord
from discord.ext import commands
from discord import app_commands
import time
import json
from typing import Optional, Tuple, List

from cogs.alerts import build_ping_embed, update_attack_log_embed, LOG_FILE

# =============================
# ⚙️ CONFIGURATION
# =============================

ATTACKER_COOLDOWN = 60          # anti-spam
ATTACKER_EXPIRATION = 120       # temps pendant lequel l’alliance attend la prochaine alerte

ATTACKER_LIST = [
    "VAE", "WBC", "BRUT", "KOBO", "HZN", "CLT", "AUTRE"
]

# =============================
# MÉMOIRE TEMPORAIRE
# =============================

pending_attackers: dict[int, tuple[str, float]] = {}
attack_cooldowns: dict[tuple[int, str], float] = {}
user_last_alert: dict[int, int] = {}  # pour appliquer sur l'alerte précédente si dispo


# =============================
# FONCTIONS UTILITAIRES
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
    except:
        return {}


def _save_logs(data: dict):
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass


# =============================
# MISE À JOUR JSON
# =============================

def update_attack_log_entry(guild_id: int, message_id: int, alliance_name: str):
    data = _load_logs()
    logs = data.get(str(guild_id), [])
    for entry in logs:
        if str(entry.get("message_id")) == str(message_id):
            entry["attackers"] = [alliance_name]
            break
    data[str(guild_id)] = logs[:30]
    _save_logs(data)


# =============================
# BOUTON D’ATTAQUE
# =============================

class AttackButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot, alliance_name: str, row: int):
        super().__init__(
            label=alliance_name,
            style=discord.ButtonStyle.danger,
            custom_id=f"att_{alliance_name}",
            row=row,
        )
        self.bot = bot
        self.alliance_name = alliance_name

    async def callback(self, interaction: discord.Interaction):
        alliance = self.alliance_name
        user_id = interaction.user.id

        await interaction.response.defer(ephemeral=True)

        # anti-spam
        if is_on_cooldown(user_id, alliance):
            await interaction.followup.send(
                f"⏱️ Attends avant de recliquer sur **{alliance}**.",
                ephemeral=True
            )
            return
        set_cooldown(user_id, alliance)

        # recherche dernière alerte du user
        msg: Optional[discord.Message] = None
        if user_id in user_last_alert:
            msg_id = user_last_alert[user_id]

            # essayer dans le salon courant
            try:
                msg = await interaction.channel.fetch_message(msg_id)  # type: ignore
            except:
                # essayer dans tous les channels
                for ch in interaction.guild.text_channels:  # type: ignore
                    try:
                        msg = await ch.fetch_message(msg_id)
                        break
                    except:
                        continue

        # si dernière alerte trouvée → mise à jour immédiate
        if msg and msg.embeds:
            emb = await build_ping_embed(msg, attackers=[alliance])
            try:
                await msg.edit(embed=emb)
            except:
                await interaction.followup.send("⚠️ Impossible de mettre à jour l’alerte.", ephemeral=True)
                return

            update_attack_log_entry(interaction.guild.id, msg.id)  # type: ignore
            await update_attack_log_embed(self.bot, interaction.guild)  # type: ignore

            await interaction.followup.send(
                f"Alliance **{alliance}** appliquée à ta dernière alerte.",
                ephemeral=True
            )
            return

        # sinon → stocker pour la prochaine alerte
        set_pending_attacker(user_id, alliance)
        await interaction.followup.send(
            f"🕒 Alliance **{alliance}** enregistrée.\n"
            "Elle sera appliquée automatiquement à ta **prochaine alerte**.",
            ephemeral=True
        )


# =============================
# PANNEAU COMPLET
# =============================

def make_attack_view(bot: commands.Bot) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for i, name in enumerate(ATTACKER_LIST):
        row = 0 if i < 4 else 1  # 4 boutons première rangée, 3 deuxième
        view.add_item(AttackButton(bot, name, row=row))
    return view


# =============================
# COG PRINCIPAL
# =============================

class AttackersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 🆕 utilisée par cogs.alerts pour mémoriser la dernière alerte créée
    def register_alert_message(self, user_id: int, message_id: int):
        user_last_alert[user_id] = message_id

    @app_commands.command(name="attackpanel", description="Affiche le panneau des alliances attaquantes.")
    async def attackpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📢 ALLIANCE ATTAQUANTE",
            description="Clique une fois sur l’alliance qui attaque (avant ou après l’alerte).",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, view=make_attack_view(self.bot))

    async def apply_pending_attacker(self, message: discord.Message, user_id: int) -> bool:
        """Appelé automatiquement lorsque l’utilisateur déclenche une alerte après avoir sélectionné une alliance."""
        alliance = get_pending_attacker(user_id)
        if not alliance:
            # même si pas d'alliance en attente,
            # on mémorise quand même cette alerte comme "dernière"
            user_last_alert[user_id] = message.id
            return False

        emb = await build_ping_embed(message, attackers=[alliance])
        try:
            await message.edit(embed=emb)
        except:
            return False

        update_attack_log_entry(message.guild.id, message.id)
        await update_attack_log_embed(self.bot, message.guild)

        if user_id in pending_attackers:
            del pending_attackers[user_id]

        # et on mémorise cette alerte comme dernière
        user_last_alert[user_id] = message.id
        return True


async def setup(bot):
    await bot.add_cog(AttackersCog(bot))
