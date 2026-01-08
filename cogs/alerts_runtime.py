# cogs/alerts_runtime.py

import discord
from discord.ext import commands

alerts_data = {}


def build_embed(base_embed, data, guild):
    embed = base_embed.copy()

    defenders = (
        "\n".join(f"<@{u}>" for u in data["defenders"])
        if data["defenders"]
        else "_Aucun pour le moment_"
    )

    if data["result"] == "win":
        result = "🏆 Victoire"
    elif data["result"] == "lose":
        result = "❌ Défaite"
    else:
        result = "⏳ En attente"

    embed.clear_fields()
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
        new_embed = build_embed(
            data["base_embed"],
            data,
            interaction.guild,
        )
        await msg.edit(embed=new_embed)

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


class AlertsRuntimeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def register_alert(self, message: discord.Message, author):
        alerts_data[message.id] = {
            "base_embed": message.embeds[0],
            "author": author.id,
            "defenders": set(),
            "result": None,
            "incomplete": False,
        }

        await message.edit(view=AlertView(message.id))

        for e in ("👍", "🏆", "❌", "😡"):
            await message.add_reaction(e)

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

        new_embed = build_embed(
            data["base_embed"],
            data,
            msg.guild,
        )
        await msg.edit(embed=new_embed)


async def setup(bot):
    await bot.add_cog(AlertsRuntimeCog(bot))
