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
# BUTTONS
# label_bouton, role_id, label_embed
# -----------------------------
BUTTONS = [
    ("Wanted", 1326671483455537172, "Def"),
    ("Attaque simultanée", 1326671483455537172, "Def"),
]


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
# ALERT
# -----------------------------
async def send_alert(
    interaction: discord.Interaction,
    cooldown_key: str,
    role_id: int,
    embed_label: str,
):
    if not check_cooldown(cooldown_key):
        return await interaction.response.send_message(
            "❌ Une alerte a déjà été envoyée récemment.",
            ephemeral=True,
        )

    channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        return await interaction.response.send_message(
            "❌ Salon d’alerte introuvable.",
            ephemeral=True,
        )

    await interaction.response.send_message(
        f"Alerte envoyée : **{cooldown_key}**.",
        ephemeral=True,
    )

    await channel.send(
        f"<@&{role_id}> les cafards se font attaquer ! 🚨"
    )

    embed = discord.Embed(
        title=f"⚠️ Percepteur attaqué : {embed_label}",
        description="Réveillez vous le fond du bus, il est temps de cafarder ! ⚠️",
        color=discord.Color.red(),
    )

    await channel.send(embed=embed)


# -----------------------------
# TEST ALERT
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
        description="Réveillez vous le fond du bus, il est temps de cafarder ! ⚠️",
        color=discord.Color.greyple(),
    )

    await channel.send(embed=embed)


# -----------------------------
# PANEL
# -----------------------------
def build_panel_view():
    view = discord.ui.View(timeout=None)

    for label, role_id, embed_label in BUTTONS:
        btn = discord.ui.Button(
            label=label,
            emoji="🪳",
            style=discord.ButtonStyle.danger,
        )

        async def callback(
            interaction,
            label=label,
            role_id=role_id,
            embed_label=embed_label,
        ):
            await send_alert(
                interaction,
                label,
                role_id,
                embed_label,
            )

        btn.callback = callback
        view.add_item(btn)

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
            description="Clique sur le bouton correspondant pour envoyer l’alerte.",
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(
            embed=embed,
            view=build_panel_view(),
        )


async def setup(bot):
    await bot.add_cog(AlertsCog(bot))
