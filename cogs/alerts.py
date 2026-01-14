# cogs/alerts.py

from __future__ import annotations

import time
import json
import os
import discord
from discord.ext import commands
from discord import app_commands

# =============================
# PERSISTENCE
# =============================
DATA_PATH = "/var/data/alerts_data.json"

def load_alerts_data() -> dict[int, dict]:
    if not os.path.exists(DATA_PATH):
        return {}

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    data: dict[int, dict] = {}
    for k, v in raw.items():
        data[int(k)] = {
            "author": v["author"],
            "channel_id": v["channel_id"],
            "defenders": set(v["defenders"]),
            "result": v["result"],
            "incomplete": v["incomplete"],
        }
    return data


def save_alerts_data():
    os.makedirs("/var/data", exist_ok=True)

    serializable = {}
    for k, v in alerts_data.items():
        serializable[str(k)] = {
            "author": v["author"],
            "channel_id": v["channel_id"],
            "defenders": list(v["defenders"]),
            "result": v["result"],
            "incomplete": v["incomplete"],
        }

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)


# =============================
# CONFIG
# =============================
ALERT_CHANNEL_ID = 1327548733398843413
ADMIN_ROLE_ID = 1280396795046006836
ROLE_TEST_ID = 1358771105980088390

MAX_DEFENDERS = 4
COOLDOWN = 30
last_ping: dict[str, float] = {}

# =============================
# BUTTONS PANEL
# =============================
BUTTONS = [
    ("WANTED", 1326671483455537172, "Def"),
    ("Attaque simultanée", 1326671483455537172, "Def"),
]

# =============================
# STATE (PERSISTANT)
# =============================
alerts_data: dict[int, dict] = load_alerts_data()


# =============================
# COOLDOWN
# =============================
def check_cooldown(key: str) -> bool:
    now = time.time()
    if key in last_ping and now - last_ping[key] < COOLDOWN:
        return False
    last_ping[key] = now
    return True


# =============================
# USER SELECT
# =============================
class DefenderSelect(discord.ui.UserSelect):
    def __init__(self, bot: commands.Bot, alert_id: int):
        super().__init__(
            placeholder="Sélectionne des défenseurs…",
            min_values=1,
            max_values=MAX_DEFENDERS,
        )
        self.bot = bot
        self.alert_id = alert_id

    async def callback(self, interaction: discord.Interaction):
        alerts_cog = self.bot.get_cog("AlertsCog")
        if not alerts_cog:
            return

        added = []
        for user in self.values:
            ok = await alerts_cog.add_defender_to_alert(self.alert_id, user.id)
            if ok:
                added.append(user.mention)

        await interaction.response.edit_message(
            content="Défenseurs ajoutés." if added else "Aucun défenseur ajouté.",
            view=None,
        )


class DefenderSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, alert_id: int):
        super().__init__(timeout=60)
        self.add_item(DefenderSelect(bot, alert_id))


class AlertView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Ajout défenseurs",
        emoji="👤",
        style=discord.ButtonStyle.success,
        custom_id="alert_add_defender",
    )
    async def defender_button(self, interaction: discord.Interaction, _):
        alert_id = interaction.message.id
        data = alerts_data.get(alert_id)
        if not data:
            return

        if interaction.user.id not in data["defenders"]:
            return await interaction.response.send_message(
                "Tu dois avoir 👍 sur l’alerte.",
                ephemeral=True,
            )

        view = DefenderSelectView(self.bot, alert_id)
        await interaction.response.send_message(
            "Sélectionne les défenseurs :",
            view=view,
            ephemeral=True,
        )


# =============================
# COG
# =============================
class AlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(AlertView(bot))

    # ---------- EMBED ----------
    def build_embed(self, data: dict) -> discord.Embed:
        color = (
            discord.Color.green() if data["result"] == "win"
            else discord.Color.red() if data["result"] == "lose"
            else discord.Color.orange()
        )

        embed = discord.Embed(title="⚠️ Percepteur attaqué", color=color)

        embed.add_field(
            name="🔔 Déclenché par",
            value=f"<@{data['author']}>",
            inline=False,
        )

        defenders = (
            ", ".join(f"<@{d}>" for d in data["defenders"])
            if data["defenders"]
            else "Aucun"
        )

        embed.add_field(
            name=f"🛡️ Défenseurs ({len(data['defenders'])}/{MAX_DEFENDERS})",
            value=defenders,
            inline=False,
        )

        etat = (
            "🏆 Victoire" if data["result"] == "win"
            else "❌ Défaite" if data["result"] == "lose"
            else "⏳ En cours"
        )

        if data["incomplete"]:
            etat += " (😡 incomplète)"

        embed.add_field(name="📊 État", value=etat, inline=False)
        return embed

    async def update_alert_message(self, alert_id: int):
        data = alerts_data.get(alert_id)
        if not data:
            return

        channel = self.bot.get_channel(data["channel_id"])
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            msg = await channel.fetch_message(alert_id)
            await msg.edit(embed=self.build_embed(data), view=AlertView(self.bot))
        except discord.HTTPException:
            pass

        save_alerts_data()

        leaderboard = self.bot.get_cog("Leaderboard")
        if leaderboard:
            await leaderboard.refresh()

    # ---------- API ----------
    async def add_defender_to_alert(self, alert_id: int, user_id: int) -> bool:
        data = alerts_data.get(alert_id)
        if not data or user_id in data["defenders"]:
            return False
        if len(data["defenders"]) >= MAX_DEFENDERS:
            return False

        data["defenders"].add(user_id)
        await self.update_alert_message(alert_id)
        return True

    async def remove_defender_from_alert(self, alert_id: int, user_id: int):
        data = alerts_data.get(alert_id)
        if not data:
            return
        data["defenders"].discard(user_id)
        await self.update_alert_message(alert_id)

    async def mark_defense_won(self, alert_id: int):
        alerts_data[alert_id]["result"] = "win"
        await self.update_alert_message(alert_id)

    async def mark_defense_lost(self, alert_id: int):
        alerts_data[alert_id]["result"] = "lose"
        await self.update_alert_message(alert_id)

    async def toggle_incomplete(self, alert_id: int):
        alerts_data[alert_id]["incomplete"] = not alerts_data[alert_id]["incomplete"]
        await self.update_alert_message(alert_id)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        if payload.message_id in alerts_data:
            alerts_data.pop(payload.message_id)
            save_alerts_data()

    # ---------- COMMANDES ----------
    async def send_alert(self, interaction, cooldown_key, role_id):
        if not check_cooldown(cooldown_key):
            return await interaction.response.send_message(
                "❌ Une alerte a déjà été envoyée récemment.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
        await interaction.response.send_message("Alerte envoyée.", ephemeral=True)

        await channel.send(f"<@&{role_id}> les cafards se font attaquer ! 🚨")

        data = {
            "author": interaction.user.id,
            "channel_id": channel.id,
            "defenders": set(),
            "result": None,
            "incomplete": False,
        }

        msg = await channel.send(embed=self.build_embed(data), view=AlertView(self.bot))
        alerts_data[msg.id] = data
        save_alerts_data()

        for e in ("👍", "🏆", "❌", "😡"):
            await msg.add_reaction(e)


async def setup(bot: commands.Bot):
    await bot.add_cog(AlertsCog(bot))
