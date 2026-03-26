# cogs/alerts.py

from __future__ import annotations

import time
import json
import os
import discord
from discord.ext import commands
from discord import app_commands

# =============================
# CONFIG
# =============================
ALERT_CHANNEL_ID = 1327548733398843413
ADMIN_ROLE_ID = 1280396795046006836
ROLE_TEST_ID = 1358771105980088390
ROLE_DEF = 1326671483455537172
ROLE_SIMU = 1328097429525893192

MAX_DEFENDERS = 4
COOLDOWN = 30
DATA_PATH = "/var/data/alerts_data.json"

last_ping: dict[str, float] = {}

BUTTONS = [
    ("WANTED", ROLE_DEF, "Def"),
    ("Attaque simultanée", (ROLE_DEF, ROLE_SIMU), "Simu"),
]

alerts_data: dict[int, dict] = {}

# =============================
# UTILS
# =============================
def check_cooldown(key: str) -> bool:
    now = time.time()
    if key in last_ping and now - last_ping[key] < COOLDOWN:
        return False
    last_ping[key] = now
    return True


# =============================
# UI
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

        for user in self.values:
            await alerts_cog.add_defender_to_alert(self.alert_id, user.id)

        await interaction.response.edit_message(
            content="Défenseurs ajoutés.",
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

    # 🟢 Ajout défenseurs
    @discord.ui.button(
        label="Ajout défenseurs",
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

    # 🔴 SOLO
    @discord.ui.button(
        label="Solo",
        style=discord.ButtonStyle.danger,
        custom_id="alert_solo",
    )
    async def solo_button(self, interaction: discord.Interaction, _):
        alert_id = interaction.message.id
        alerts_cog = self.bot.get_cog("AlertsCog")
        if not alerts_cog:
            return

        await alerts_cog.delete_alert(
            alert_id,
            interaction.channel,
            interaction.user,
        )

        await interaction.response.defer()


# =============================
# COG
# =============================
class AlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.alert_view = AlertView(bot)
        bot.add_view(self.alert_view)
        self.load_data()

    # ---------- PERSISTENCE ----------
    def load_data(self):
        if not os.path.exists(DATA_PATH):
            return

        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)

            alerts_data.clear()
            for k, v in raw.items():
                alerts_data[int(k)] = {
                    "author": v["author"],
                    "channel_id": v["channel_id"],
                    "defenders": set(v["defenders"]),
                    "result": v["result"],
                    "incomplete": v["incomplete"],
                }
        except Exception:
            alerts_data.clear()

    def save_data(self):
        os.makedirs("/var/data", exist_ok=True)
        serializable = {
            str(k): {
                "author": v["author"],
                "channel_id": v["channel_id"],
                "defenders": list(v["defenders"]),
                "result": v["result"],
                "incomplete": v["incomplete"],
            }
            for k, v in alerts_data.items()
        }

        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)

    # ---------- EMBED ----------
    def build_embed(self, data: dict, title_override: str | None = None) -> discord.Embed:
        color = (
            discord.Color.green() if data["result"] == "win"
            else discord.Color.red() if data["result"] == "lose"
            else discord.Color.orange()
        )

        title = title_override or "⚠️ Percepteur attaqué"

        embed = discord.Embed(title=title, color=color)

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

    async def update_alert_message(self, alert_id: int, title_override: str | None = None):
        data = alerts_data.get(alert_id)
        if not data:
            return

        channel = self.bot.get_channel(data["channel_id"])
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            msg = await channel.fetch_message(alert_id)
            await msg.edit(embed=self.build_embed(data, title_override), view=self.alert_view)
        except discord.HTTPException:
            pass

        self.save_data()

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

    async def delete_alert(
        self,
        alert_id: int,
        channel: discord.abc.Messageable,
        user: discord.User | discord.Member,
    ):
        if alert_id not in alerts_data:
            return

        alerts_data.pop(alert_id, None)
        self.save_data()

        try:
            msg = await channel.fetch_message(alert_id)
            await msg.delete()
        except discord.HTTPException:
            pass

        username = user.display_name
        await channel.send(
            f"Une alerte a été supprimée par {username} : 1 seul attaquant"
        )

    async def send_alert(self, interaction, cooldown_key, roles, title_override: str | None = None):
        if not check_cooldown(cooldown_key):
            return await interaction.response.send_message(
                "❌ Une alerte a déjà été envoyée récemment.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
        await interaction.response.send_message("Alerte envoyée.", ephemeral=True)

        if isinstance(roles, int):
            roles = [roles]

        mention_roles = " ".join(f"<@&{r}>" for r in roles)
        await channel.send(f"{mention_roles} 🚨")

        data = {
            "author": interaction.user.id,
            "channel_id": channel.id,
            "defenders": set(),
            "result": None,
            "incomplete": False,
        }

        msg = await channel.send(embed=self.build_embed(data, title_override), view=self.alert_view)
        alerts_data[msg.id] = data
        self.save_data()

        for e in ("👍", "🏆", "❌", "😡"):
            await msg.add_reaction(e)

    async def send_test_alert(self, interaction):
        if not any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles):
            return await interaction.response.send_message("Admin only.", ephemeral=True)

        channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
        await interaction.response.send_message("Alerte TEST envoyée.", ephemeral=True)

        await channel.send(f"<@&{ROLE_TEST_ID}>")

        data = {
            "author": interaction.user.id,
            "channel_id": channel.id,
            "defenders": set(),
            "result": None,
            "incomplete": False,
        }

        msg = await channel.send(embed=self.build_embed(data), view=self.alert_view)
        alerts_data[msg.id] = data
        self.save_data()

        for e in ("👍", "🏆", "❌", "😡"):
            await msg.add_reaction(e)

    @app_commands.command(
    name="pingpanel",
    description="Affiche le panneau de ping défense.",
)
async def pingpanel(self, interaction: discord.Interaction):
    view = discord.ui.View(timeout=None)

    for label, role_id, key in BUTTONS:
        async def callback(i, role_id=role_id, key=key):
            # Pour "Attaque simultanée", on ping le rôle Def + rôle Simu
            if label == "Attaque simultanée":
                role_def = role_id
                role_simu = 1328097429525893192
                await self.send_alert(i, key, role_def)
                await self.send_alert(i, key, role_simu)
            else:
                await self.send_alert(i, key, role_id)

        btn = discord.ui.Button(
            label=label,
            emoji="⚔️" if label == "WANTED" else "💣",
            style=discord.ButtonStyle.primary if label == "WANTED" else discord.ButtonStyle.danger,
        )
        btn.callback = callback
        view.add_item(btn)

    # Bouton TEST
    test_btn = discord.ui.Button(label="TEST", style=discord.ButtonStyle.secondary)

    async def test_cb(i):
        await self.send_test_alert(i)

    test_btn.callback = test_cb
    view.add_item(test_btn)

    embed = discord.Embed(
        title="⚔️ Ping défense percepteurs",
        description="Clique sur le bouton correspondant pour envoyer l’alerte.",
        color=discord.Color.blurple(),
    )

    await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(AlertsCog(bot))
