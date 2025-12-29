# cogs/alerts.py

import time
import discord
from discord.ext import commands
from discord import app_commands

# -----------------------------
# CONFIG
# -----------------------------
ALERT_CHANNEL_ID = 1327548733398843413  # Salon où envoyer les alertes
ADMIN_ROLE_ID = 1280396795046006836     # Rôle admin
ROLE_TEST_ID = 1358771105980088390      # Rôle pingé par le bouton TEST

# Cooldown (30 sec par team)
COOLDOWN = 30
last_ping: dict[str, float] = {}


# -----------------------------
# TEAMS
# -----------------------------
TEAMS = [
    ("Def", 1326671483455537172),
]


# -----------------------------
# HELPER : CHECK COOLDOWN
# -----------------------------
def check_cooldown(key: str) -> bool:
    now = time.time()
    if key in last_ping and now - last_ping[key] < COOLDOWN:
        return False
    last_ping[key] = now
    return True


# -----------------------------
# SEND ALERT FUNCTION
# -----------------------------
async def send_team_alert(
    interaction: discord.Interaction,
    label: str,
    role_id: int,
    blue: bool = False,
):
    if not check_cooldown(label):
        return await interaction.response.send_message(
            "❌ Une alerte pour cette team a déjà été envoyée récemment.",
            ephemeral=True,
        )

    channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        return await interaction.response.send_message(
            "❌ Salon d’alerte introuvable.",
            ephemeral=True,
        )

    await interaction.response.send_message(
        f"Alerte envoyée pour **{label}**.",
        ephemeral=True,
    )

    await channel.send(f"<@&{role_id}>")

    embed = discord.Embed(
        title=f"⚠️ Percepteur attaqué : {label}",
        description=f"Déclenché par {interaction.user.mention}",
        color=discord.Color.blue() if blue else discord.Color.red(),
    )

    await channel.send(embed=embed)


# -----------------------------
# SEND TEST ALERT (ADMIN ONLY)
# -----------------------------
async def send_test_alert(interaction: discord.Interaction):
    if not any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles):
        return await interaction.response.send_message(
            "Admin only.",
            ephemeral=True,
        )

    channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        return await interaction.response.send_message(
            "❌ Salon d’alerte introuvable.",
            ephemeral=True,
        )

    await interaction.response.send_message(
        "Alerte TEST envoyée.",
        ephemeral=True,
    )

    await channel.send(f"<@&{ROLE_TEST_ID}>")

    embed = discord.Embed(
        title="⚠️ Percepteur attaqué : TEST",
        description=f"Déclenché par {interaction.user.mention}",
        color=discord.Color.greyple(),
    )

    await channel.send(embed=embed)


# -----------------------------
# PANEL VIEW
# -----------------------------
def build_panel_view():
    view = discord.ui.View(timeout=None)

    # Teams
    for label, role_id in TEAMS:

        style = (
            discord.ButtonStyle.primary
            if label == "Prisme"
            else discord.ButtonStyle.danger
        )

        btn = discord.ui.Button(
            label=label,
            style=style,
        )

        async def callback(
            interaction,
            label=label,
            role_id=role_id,
            style=style,
        ):
            await send_team_alert(
                interaction,
                label,
                role_id,
                blue=(style == discord.ButtonStyle.primary),
            )

        btn.callback = callback
        view.add_item(btn)

    # Bouton TEST (admin only)
    test_btn = discord.ui.Button(
        label="TEST",
        style=discord.ButtonStyle.secondary,
    )

    async def test_cb(interaction):
        await send_test_alert(interaction)

    test_btn.callback = test_cb
    view.add_item(test_btn)

    return view


# -----------------------------
# COG
# -----------------------------
class AlertsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="pingpanel",
        description="Affiche le panneau de ping défense.",
    )
    async def pingpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚔️ Ping défense percepteurs",
            description="Clique sur la guilde attaquée pour envoyer l’alerte.",
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(
            embed=embed,
            view=build_panel_view(),
        )


async def setup(bot):
    await bot.add_cog(AlertsCog(bot))
