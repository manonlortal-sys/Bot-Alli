import time
import discord
from discord.ext import commands

ALERT_CHANNEL_ID = 1327548733398843413
COOLDOWN = 30

last_ping = {}
alerts_data = {}

def check_cooldown(key):
    now = time.time()
    if key in last_ping and now - last_ping[key] < COOLDOWN:
        return False
    last_ping[key] = now
    return True


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
        "\n".join(f"<@{u}>" for u in data["defenders"])
        if data["defenders"]
        else "_Aucun pour le moment_"
    )

    result = "⏳ En attente"
    if data["result"] == "win":
        result = "🏆 Victoire"
    elif data["result"] == "lose":
        result = "❌ Défaite"

    embed.add_field(name="🛡️ Défenseurs", value=defenders, inline=False)
    embed.add_field(name="📊 Résultat", value=result, inline=False)

    if data["incomplete"]:
        embed.add_field(
            name="⚠️ État",
            value="😡 Défense incomplète",
            inline=False,
        )

    return embed


class AddDefenderModal(discord.ui.Modal, title="Ajouter défenseurs"):
    mentions = discord.ui.TextInput(
        label="Mentions (max 4)",
        placeholder="@Pseudo1 @Pseudo2",
        required=True,
    )

    def __init__(self, message_id):
        super().__init__()
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        data = alerts_data[self.message_id]

        if interaction.user.id not in data["defenders"]:
            return await interaction.response.send_message(
                "Tu dois avoir 👍 pour ajouter des défenseurs.",
                ephemeral=True,
            )

        for u in interaction.mentions[:4]:
            data["defenders"].add(u.id)

        msg = await interaction.channel.fetch_message(self.message_id)
        await msg.edit(
            embed=build_embed(
                interaction.guild.get_member(data["author"]),
                data,
            )
        )

        await interaction.response.send_message(
            "Défenseur(s) ajouté(s).",
            ephemeral=True,
        )


class AlertView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.Button(
        label="Ajouter défenseur",
        emoji="👤",
        style=discord.ButtonStyle.secondary,
    )
    async def add_defender(self, interaction, _):
        await interaction.response.send_modal(
            AddDefenderModal(self.message_id)
        )


class AlertsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def send_alert(self, interaction, key, role_id, embed_label):
        if not check_cooldown(key):
            return await interaction.response.send_message(
                "❌ Une alerte a déjà été envoyée récemment.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"Alerte envoyée : **{key}**.",
            ephemeral=True,
        )

        channel = interaction.guild.get_channel(ALERT_CHANNEL_ID)

        await channel.send(
            f"<@&{role_id}> les cafards se font attaquer ! 🚨"
        )

        data = {
            "author": interaction.user.id,
            "defenders": set(),
            "result": None,
            "incomplete": False,
        }

        embed = build_embed(interaction.user, data)
        msg = await channel.send(embed=embed, view=AlertView(0))

        alerts_data[msg.id] = data
        await msg.edit(view=AlertView(msg.id))

        for e in ("👍", "🏆", "❌", "😡"):
            await msg.add_reaction(e)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        data = alerts_data.get(reaction.message.id)
        if not data:
            return

        emoji = str(reaction.emoji)

        if emoji == "👍":
            data["defenders"].add(user.id)
        elif emoji == "🏆":
            data["result"] = "win"
            await reaction.message.clear_reaction("❌")
        elif emoji == "❌":
            data["result"] = "lose"
            await reaction.message.clear_reaction("🏆")
        elif emoji == "😡":
            data["incomplete"] = True

        await reaction.message.edit(
            embed=build_embed(
                reaction.message.guild.get_member(data["author"]),
                data,
            )
        )


async def setup(bot):
    await bot.add_cog(AlertsCog(bot))
