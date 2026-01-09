# cogs/alerts.py

import time
import discord
from discord.ext import commands
from discord import app_commands

# -----------------------------
# CONFIG
# -----------------------------
ALERT_CHANNEL_ID = 1327548733398843413
ADMIN_ROLE_ID = 1280396795046006836
ROLE_TEST_ID = 1358771105980088390

COOLDOWN = 30
last_ping: dict[str, float] = {}

# -----------------------------
# BUTTONS PANEL (INCHANGÉ)
# -----------------------------
BUTTONS = [
    ("WANTED", 1326671483455537172, "Def"),
    ("Attaque simultanée", 1326671483455537172, "Def"),
]

# -----------------------------
# STATE CENTRAL
# -----------------------------
alerts_data = {}  # message_id -> dict


# -----------------------------
# COOLDOWN
# -----------------------------
def check_cooldown(key: str) -> bool:
    now = time.time()
    if key in last_ping and now - last_ping[key] < COOLDOWN:
        return False
    last_ping[key] = now
    return True


# -----------------------------
# USER SELECT
# -----------------------------
class DefenderSelect(discord.ui.UserSelect):
    def __init__(self, alert_id: int):
        super().__init__(
            placeholder="Sélectionne des défenseurs…",
            min_values=1,
            max_values=4,
        )
        self.alert_id = alert_id

    async def callback(self, interaction: discord.Interaction):
        data = alerts_data.get(self.alert_id)
        if not data:
            return await interaction.response.send_message(
                "Alerte inexistante.",
                ephemeral=True,
            )

        if interaction.user.id not in data["defenders"]:
            return await interaction.response.send_message(
                "Tu dois avoir 👍 sur l’alerte.",
                ephemeral=True,
            )

        for user in self.values:
            data["defenders"].add(user.id)

        alerts_cog = interaction.client.get_cog("AlertsCog")
        if alerts_cog:
            await alerts_cog.update_alert_message(self.alert_id)

        await interaction.response.send_message(
            "Défenseurs ajoutés.",
            ephemeral=True,
        )


class DefenderSelectView(discord.ui.View):
    def __init__(self, alert_id: int):
        super().__init__(timeout=60)
        self.add_item(DefenderSelect(alert_id))


# -----------------------------
# VIEW MESSAGE ALERTE (NON PERSISTANTE)
# -----------------------------
class AlertView(discord.ui.View):
    def __init__(self, alert_id: int):
        super().__init__(timeout=None)
        self.alert_id = alert_id

    @discord.ui.Button(
        label="Ajouter défenseur",
        emoji="👤",
        style=discord.ButtonStyle.secondary,
    )
    async def add_defender(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        data = alerts_data.get(self.alert_id)
        if not data:
            return await interaction.response.send_message(
                "Alerte inexistante.",
                ephemeral=True,
            )

        if interaction.user.id not in data["defenders"]:
            return await interaction.response.send_message(
                "Tu dois avoir 👍 sur l’alerte.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            "Sélectionne les défenseurs :",
            view=DefenderSelectView(self.alert_id),
            ephemeral=True,
        )


# -----------------------------
# COG
# -----------------------------
class AlertsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------- EMBED ----------
    def build_embed(self, data: dict) -> discord.Embed:
        embed = discord.Embed(
            title="⚠️ Percepteur attaqué",
            color=discord.Color.red(),
        )

        embed.add_field(
            name="Déclenché par",
            value=f"<@{data['author']}>",
            inline=False,
        )

        defenders = (
            ", ".join(f"<@{u}>" for u in data["defenders"])
            if data["defenders"]
            else "Aucun"
        )
        embed.add_field(
            name="🛡️ Défenseurs",
            value=defenders,
            inline=False,
        )

        if data["result"] == "win":
            result = "🏆 Victoire"
        elif data["result"] == "lose":
            result = "❌ Défaite"
        else:
            result = "⏳ En cours"

        embed.add_field(
            name="📊 Résultat",
            value=result,
            inline=False,
        )

        if data["incomplete"]:
            embed.add_field(
                name="⚠️ État",
                value="😡 Défense incomplète",
                inline=False,
            )

        return embed

    async def update_alert_message(self, message_id: int):
        data = alerts_data.get(message_id)
        if not data:
            return

        channel = self.bot.get_channel(data["channel_id"])
        if not channel:
            return

        try:
            msg = await channel.fetch_message(message_id)
        except discord.HTTPException:
            return

        await msg.edit(
            embed=self.build_embed(data),
            view=AlertView(message_id),
        )

    # ---------- API RÉACTIONS ----------
    async def add_defender(self, message_id: int, user_id: int):
        alerts_data[message_id]["defenders"].add(user_id)
        await self.update_alert_message(message_id)

    async def remove_defender(self, message_id: int, user_id: int):
        alerts_data[message_id]["defenders"].discard(user_id)
        await self.update_alert_message(message_id)

    async def set_result(self, message_id: int, result: str):
        alerts_data[message_id]["result"] = result
        await self.update_alert_message(message_id)

    async def clear_result(self, message_id: int):
        alerts_data[message_id]["result"] = None
        await self.update_alert_message(message_id)

    async def toggle_incomplete(self, message_id: int):
        alerts_data[message_id]["incomplete"] = not alerts_data[message_id]["incomplete"]
        await self.update_alert_message(message_id)

    async def clear_incomplete(self, message_id: int):
        alerts_data[message_id]["incomplete"] = False
        await self.update_alert_message(message_id)

    # ---------- ALERT ----------
    async def send_alert(self, interaction, cooldown_key, role_id):
        if not check_cooldown(cooldown_key):
            return await interaction.response.send_message(
                "❌ Alerte déjà envoyée récemment.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
        if not channel:
            return

        await interaction.response.send_message(
            f"Alerte envoyée : **{cooldown_key}**.",
            ephemeral=True,
        )

        await channel.send(f"<@&{role_id}> les cafards se font attaquer ! 🚨")

        data = {
            "author": interaction.user.id,
            "channel_id": channel.id,
            "defenders": set(),
            "result": None,
            "incomplete": False,
        }

        msg = await channel.send(
            embed=self.build_embed(data),
            view=AlertView(0),
        )

        alerts_data[msg.id] = data
        await msg.edit(view=AlertView(msg.id))

        for e in ("👍", "🏆", "❌", "😡"):
            await msg.add_reaction(e)

    # ---------- TEST ----------
    async def send_test_alert(self, interaction):
        if not any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles):
            return await interaction.response.send_message(
                "Admin only.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
        if not channel:
            return

        await interaction.response.send_message(
            "Alerte TEST envoyée.",
            ephemeral=True,
        )

        await channel.send(f"<@&{ROLE_TEST_ID}>")

        data = {
            "author": interaction.user.id,
            "channel_id": channel.id,
            "defenders": set(),
            "result": None,
            "incomplete": False,
        }

        msg = await channel.send(
            embed=self.build_embed(data),
            view=AlertView(0),
        )

        alerts_data[msg.id] = data
        await msg.edit(view=AlertView(msg.id))

        for e in ("👍", "🏆", "❌", "😡"):
            await msg.add_reaction(e)

    # ---------- PANEL ----------
    @app_commands.command(
        name="pingpanel",
        description="Affiche le panneau de ping défense.",
    )
    async def pingpanel(self, interaction: discord.Interaction):
        view = discord.ui.View(timeout=None)

        for label, role_id, key in BUTTONS:
            async def callback(i, role_id=role_id, key=key):
                await self.send_alert(i, key, role_id)

            btn = discord.ui.Button(
                label=label,
                emoji="🪳",
                style=discord.ButtonStyle.primary if label == "WANTED" else discord.ButtonStyle.danger,
            )
            btn.callback = callback
            view.add_item(btn)

        async def test_cb(i):
            await self.send_test_alert(i)

        test_btn = discord.ui.Button(
            label="TEST",
            style=discord.ButtonStyle.secondary,
        )
        test_btn.callback = test_cb
        view.add_item(test_btn)

        embed = discord.Embed(
            title="⚔️ Ping défense percepteurs",
            description="Clique sur le bouton correspondant pour envoyer l’alerte.",
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(AlertsCog(bot))