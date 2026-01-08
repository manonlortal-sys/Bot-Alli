# cogs/alerts_runtime.py

import discord
from discord.ext import commands

alerts_data = {}  # message_id -> state


def update_embed(embed: discord.Embed, data: dict) -> discord.Embed:
    # On nettoie uniquement les champs dynamiques
    embed.clear_fields()

    defenders = (
        "\n".join(f"<@{u}>" for u in data["defenders"])
        if data["defenders"]
        else "_Aucun pour le moment_"
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
        result = "⏳ En attente"

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

        for u in interaction.mentions[:4]:
            data["defenders"].add(u.id)

        msg = await interaction.channel.fetch_message(self.message_id)
        embed = msg.embeds[0]

        await msg.edit(embed=update_embed(embed, data))

        await interaction.response.send_message(
            "Défenseur(s) ajouté(s).",
            ephemeral=True,
        )


class AlertView(discord.ui.View):
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


class AlertsRuntimeCog(commands.Cog, name="AlertsRuntimeCog"):
    def __init__(self, bot):
        self.bot = bot

    async def register_alert(self, message: discord.Message, author):
        if not message.embeds:
            return

        alerts_data[message.id] = {
            "author": author.id,
            "defenders": set(),
            "result": None,      # win / lose
            "incomplete": False,
        }

        await message.edit(view=AlertView(message.id))

        for e in ("👍", "🏆", "❌", "😡"):
            await message.add_reaction(e)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        data = alerts_data.get(payload.message_id)
        if not data:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(payload.channel_id)

        msg = await channel.fetch_message(payload.message_id)
        embed = msg.embeds[0]
        emoji = str(payload.emoji)

        if emoji == "👍":
            data["defenders"].add(payload.user_id)

        elif emoji == "🏆":
            data["result"] = "win"
            await msg.clear_reaction("❌")

        elif emoji == "❌":
            data["result"] = "lose"
            await msg.clear_reaction("🏆")

        elif emoji == "😡":
            data["incomplete"] = True

        await msg.edit(embed=update_embed(embed, data))


async def setup(bot):
    await bot.add_cog(AlertsRuntimeCog(bot))
