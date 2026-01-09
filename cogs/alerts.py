# cogs/alerts.py

from __future__ import annotations

import time
import discord
from discord.ext import commands
from discord import app_commands

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
# BUTTONS PANEL (INCHANGÉ)
# =============================
BUTTONS = [
    ("WANTED", 1326671483455537172, "Def"),
    ("Attaque simultanée", 1326671483455537172, "Def"),
]

# =============================
# STATE
# =============================
alerts_data: dict[int, dict] = {}


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
        alerts_cog: AlertsCog | None = self.bot.get_cog("AlertsCog")  # type: ignore
        if not alerts_cog:
            return await interaction.response.edit_message(
                content="Système d’alertes indisponible.",
                view=None,
            )

        data = alerts_data.get(self.alert_id)
        if not data:
            return await interaction.response.edit_message(
                content="Cette alerte n'existe plus.",
                view=None,
            )

        if len(data["defenders"]) >= MAX_DEFENDERS:
            return await interaction.response.edit_message(
                content=f"Limite de {MAX_DEFENDERS} défenseurs atteinte.",
                view=None,
            )

        added = []
        for user in self.values:
            if len(data["defenders"]) >= MAX_DEFENDERS:
                break
            ok = await alerts_cog.add_defender_to_alert(self.alert_id, user.id)
            if ok:
                added.append(user.mention)

        msg = (
            "Défenseurs ajoutés : " + ", ".join(added)
            if added
            else "Aucun défenseur ajouté."
        )
        await interaction.response.edit_message(content=msg, view=None)


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
    async def defender_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True)

        alert_id = interaction.message.id
        data = alerts_data.get(alert_id)
        if not data:
            return await interaction.followup.send(
                "Cette alerte n'existe plus.",
                ephemeral=True,
            )

        if interaction.user.id not in data["defenders"]:
            return await interaction.followup.send(
                "Tu dois avoir 👍 sur l’alerte.",
                ephemeral=True,
            )

        if len(data["defenders"]) >= MAX_DEFENDERS:
            return await interaction.followup.send(
                f"Limite de {MAX_DEFENDERS} défenseurs atteinte.",
                ephemeral=True,
            )

        view = DefenderSelectView(self.bot, alert_id)
        await interaction.followup.send(
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
        self.alert_view = AlertView(bot)
        bot.add_view(self.alert_view)

    # ---------- EMBED ----------
    def build_embed(self, data: dict) -> discord.Embed:
        if data["result"] == "win":
            color = discord.Color.green()
        elif data["result"] == "lose":
            color = discord.Color.red()
        else:
            color = discord.Color.orange()

        embed = discord.Embed(
            title="⚠️ Percepteur attaqué",
            color=color,
        )

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

        if data["result"] == "win":
            etat = "🏆 Victoire"
        elif data["result"] == "lose":
            etat = "❌ Défaite"
        else:
            etat = "⏳ En cours"

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
        except discord.HTTPException:
            return

        await msg.edit(embed=self.build_embed(data), view=self.alert_view)

        # ✅ SYNC LEADERBOARD (CORRECTION CLÉ)
        leaderboard = self.bot.get_cog("Leaderboard")
        if leaderboard:
            await leaderboard.refresh()

    # ---------- API ----------
    async def add_defender_to_alert(self, alert_id: int, user_id: int) -> bool:
        data = alerts_data.get(alert_id)
        if not data:
            return False
        if user_id in data["defenders"]:
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
        data = alerts_data.get(alert_id)
        if not data:
            return
        data["result"] = "win"
        await self.update_alert_message(alert_id)

    async def mark_defense_lost(self, alert_id: int):
        data = alerts_data.get(alert_id)
        if not data:
            return
        data["result"] = "lose"
        await self.update_alert_message(alert_id)

    async def toggle_incomplete(self, alert_id: int):
        data = alerts_data.get(alert_id)
        if not data:
            return
        data["incomplete"] = not data["incomplete"]
        await self.update_alert_message(alert_id)

    # ---------- ALERT ----------
    async def send_alert(self, interaction, cooldown_key, role_id):
        if not check_cooldown(cooldown_key):
            return await interaction.response.send_message(
                "❌ Une alerte a déjà été envoyée récemment.",
                ephemeral=True,
            )

        channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ Salon d’alerte introuvable.",
                ephemeral=True,
            )

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

        msg = await channel.send(embed=self.build_embed(data), view=self.alert_view)
        alerts_data[msg.id] = data

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
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ Salon d’alerte introuvable.",
                ephemeral=True,
            )

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

        msg = await channel.send(embed=self.build_embed(data), view=self.alert_view)
        alerts_data[msg.id] = data

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
                style=discord.ButtonStyle.primary
                if label.lower() == "wanted"
                else discord.ButtonStyle.danger,
            )
            btn.callback = callback
            view.add_item(btn)

        test_btn = discord.ui.Button(
            label="TEST",
            style=discord.ButtonStyle.secondary,
        )

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