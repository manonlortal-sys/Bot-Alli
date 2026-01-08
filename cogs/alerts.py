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
# MEMORY (runtime only)
# -----------------------------
alerts_data = {}  # message_id -> data


def new_alert(author_id: int):
    return {
        "author": author_id,
        "defenders": set(),
        "result": None,      # "win" | "lose"
        "incomplete": False,
    }


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
# EMBED
# -----------------------------
def build_embed(author, data):
    embed = discord.Embed(
        title="⚠️ Percepteur attaqué — Défense en cours",
        description=(
            "Réveillez-vous le fond du bus, il est temps de cafarder 🚨\n\n"
            f"Déclenché par {author.mention}"
        ),
        color=discord.Color.red(),
    )

    defenders = (
        "\n".join(f"<@{uid}>" for uid in data["defenders"])
        if data["defenders"]
        else "_Aucun pour le moment_"
    )

    if data["result"] == "win":
        result = "🏆 Victoire"
    elif data["result"] == "lose":
        result = "❌ Défaite"
    else:
        result = "⏳ En attente"

    embed.add_field(name="🛡️ Défenseurs", value=defenders, inline=False)
    embed.add_field(name="📊 Résultat", value=result, inline=False)

    if data["incomplete"]:
        embed.add_field(
            name="⚠️ État",
            value="😡 Défense incomplète",
            inline=False,
        )

    return embed


# -----------------------------
# MODAL AJOUT DEFENSEUR
# -----------------------------
class AddDefenderModal(discord.ui.Modal, title="Ajouter défenseurs"):
    mentions = discord.ui.TextInput(
        label="Mentions (max 4)",
        placeholder="@Pseudo1 @Pseudo2",
        required=True,
    )

    def __init__(self, message_id: int):
        super().__init__()
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        data = alerts_data.get(self.message_id)
        if not data:
            return await interaction.response.send_message(
                "Alerte inconnue.",
                ephemeral=True,
            )

        if interaction.user.id not in data["defenders"]:
            return await interaction.response.send_message(
                "Tu dois avoir 👍 pour ajouter des défenseurs.",
                ephemeral=True,
            )

        for user in interaction.mentions[:4]:
            data["defenders"].add(user.id)

        msg = await interaction.channel.fetch_message(self.message_id)
        author = interaction.guild.get_member(data["author"])
        await msg.edit(embed=build_embed(author, data))

        await interaction.response.send_message(
            "Défenseur(s) ajouté(s).",
            ephemeral=True,
        )


# -----------------------------
# VIEW MESSAGE ALERTE
# -----------------------------
class AlertMessageView(discord.ui.View):
    def __init__(self, message_id: int):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.Button(
        label="Ajouter défenseur",
        emoji="👤",
        style=discord.ButtonStyle.secondary,
    )
    async def add_defender(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(
            AddDefenderModal(self.message_id)
        )


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

    # message ping (INCHANGÉ)
    await channel.send(f"<@&{role_id}> les cafards se font attaquer ! 🚨")

    # message embed (AMÉLIORÉ)
    data = new_alert(interaction.user.id)
    embed = build_embed(interaction.user, data)

    msg = await channel.send(embed=embed)
    alerts_data[msg.id] = data

    await msg.edit(view=AlertMessageView(msg.id))

    for e in ("👍", "🏆", "❌", "😡"):
        await msg.add_reaction(e)


# -----------------------------
# TEST ALERT (INCHANGÉ)
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
        description=(
            "Réveillez vous le fond du bus, il est temps de cafarder ! ⚠️\n\n"
            f"Déclenché par {interaction.user.mention}"
        ),
        color=discord.Color.greyple(),
    )

    await channel.send(embed=embed)


# -----------------------------
# PANEL (STRICTEMENT INCHANGÉ)
# -----------------------------
def build_panel_view():
    view = discord.ui.View(timeout=None)

    for label, role_id, embed_label in BUTTONS:
        btn = discord.ui.Button(
            label=label,
            emoji="🪳",
            style=(
                discord.ButtonStyle.primary
                if label.lower() == "wanted"
                else discord.ButtonStyle.danger
            ),
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

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        msg = reaction.message
        data = alerts_data.get(msg.id)
        if not data:
            return

        emoji = str(reaction.emoji)

        if emoji == "👍":
            data["defenders"].add(user.id)

        elif emoji == "🏆":
            data["result"] = "win"
            await msg.clear_reaction("❌")

        elif emoji == "❌":
            data["result"] = "lose"
            await msg.clear_reaction("🏆")

        elif emoji == "😡":
            data["incomplete"] = True

        author = msg.guild.get_member(data["author"])
        await msg.edit(embed=build_embed(author, data))

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
