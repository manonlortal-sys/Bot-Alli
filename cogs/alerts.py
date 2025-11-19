# cogs/alerts.py

import time
import discord
from discord.ext import commands
from discord import app_commands

# -----------------------------
# CONFIG
# -----------------------------
ALERT_CHANNEL_ID = 1139550892471889971  # Salon où envoyer les alertes
ADMIN_ROLE_ID = 1139578015676895342     # Rôle admin
ROLE_TEST_ID = 1421867268421320844      # Rôle pingé par le bouton TEST

# Cooldown (30 sec par team + rush simu)
COOLDOWN = 30
last_ping: dict[str, float] = {}

# -----------------------------
# EMOJIS CUSTOM (définitifs)
# -----------------------------
TEAM_EMOJIS = {
    "Wanted": "<:Wanted:1421870161048375357>",
    "Wanted 2": "<:Wanted:1421870161048375357>",
    "Snowflake": "<:Snowflake:1421870090588131441>",
    "Secteur K": "<:SecteurK:1421870011902988439>",
    "Rixe": "<:Rixe:1438158988742230110>",
    "HagraTime": "<:HagraTime:1422120372836503622>",
    "HagraPaLtime": "<:HagraPasLtime:1422120467812323339>",
    "Ruthless": "<:Ruthless:1438157046770827304>",
    "Prisme": "<:Prisme:1440376012444663868>",
}

# -----------------------------
# TEAMS & PANEL ORDER (4x3)
# -----------------------------
TEAMS = [
    ("Wanted",        1419320456263237663),
    ("Wanted 2",      1421860260377006295),
    ("Snowflake",     1421859079755927682),
    ("Secteur K",     1419320615999111359),

    ("Rixe",          1421927584802934915),
    ("HagraTime",     1421927858967810110),
    ("HagraPaLtime",  1421927953188524144),
    ("Ruthless",      1437841408856948776),

    ("Prisme",        1421953218719518961),  # bleu
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
async def send_team_alert(interaction: discord.Interaction, label: str, role_id: int, blue: bool = False):
    if not check_cooldown(label):
        return await interaction.response.send_message(
            "❌ Une alerte pour cette team a déjà été envoyée récemment.",
            ephemeral=True,
        )

    channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        return await interaction.response.send_message("❌ Salon d’alerte introuvable.", ephemeral=True)

    emoji = TEAM_EMOJIS.get(label, "")

    await interaction.response.send_message(
        f"Alerte envoyée pour **{label}**.",
        ephemeral=True,
    )

    await channel.send(f"<@&{role_id}>")

    embed = discord.Embed(
        title=f"⚠️ Percepteur attaqué : {label} {emoji}",
        description=f"Déclenché par {interaction.user.mention}",
        color=discord.Color.blue() if blue else discord.Color.red(),
    )

    await channel.send(embed=embed)


# -----------------------------
# SEND RUSH SIMU ALERT
# -----------------------------
async def send_rush_simu(interaction: discord.Interaction):
    key = "RUSH_SIMU"

    if not check_cooldown(key):
        return await interaction.response.send_message(
            "❌ Une alerte Rush Simu a déjà été envoyée récemment.",
            ephemeral=True,
        )

    channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        return await interaction.response.send_message("❌ Salon d’alerte introuvable.", ephemeral=True)

    await interaction.response.send_message("Alerte Rush Simu envoyée.", ephemeral=True)

    # Ping everyone hors embed
    await channel.send("@everyone")

    embed = discord.Embed(
        title="⚠️ On se fait rush !",
        description=(
            "🔥 Une guilde de l’alliance se fait attaquer simultanément,\n"
            "ou toute l’alliance se fait rush.\n"
            "Merci de vous connecter pour aider !"
        ),
        color=discord.Color.blue(),
    )

    await channel.send(embed=embed)


# -----------------------------
# SEND TEST ALERT (ADMIN ONLY)
# -----------------------------
async def send_test_alert(interaction: discord.Interaction):
    if not any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles):
        return await interaction.response.send_message("Admin only.", ephemeral=True)

    channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)
    if not channel:
        return await interaction.response.send_message("❌ Salon d’alerte introuvable.", ephemeral=True)

    await interaction.response.send_message("Alerte TEST envoyée.", ephemeral=True)

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

    # Les 9 teams
    for label, role_id in TEAMS:

        # Bouton bleu pour Prisme
        style = discord.ButtonStyle.primary if label == "Prisme" else discord.ButtonStyle.danger

        btn = discord.ui.Button(
            label=label,
            emoji=TEAM_EMOJIS[label],
            style=style,
        )

        async def callback(interaction, label=label, role_id=role_id, style=style):
            await send_team_alert(interaction, label, role_id, blue=(style == discord.ButtonStyle.primary))

        btn.callback = callback
        view.add_item(btn)

    # Bouton Rush Simu
    rush_btn = discord.ui.Button(
        label="RUSH SIMU",
        emoji="🔥",
        style=discord.ButtonStyle.primary,
    )

    async def rush_cb(interaction):
        await send_rush_simu(interaction)

    rush_btn.callback = rush_cb
    view.add_item(rush_btn)

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

    @app_commands.command(name="pingpanel", description="Affiche le panneau de ping défense.")
    async def pingpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚔️ Ping défense percepteurs",
            description="Clique sur la guilde attaquée pour envoyer l’alerte.",
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(embed=embed, view=build_panel_view())


async def setup(bot):
    await bot.add_cog(AlertsCog(bot))
