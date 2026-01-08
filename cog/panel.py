import discord
from discord.ext import commands
from discord import app_commands

ALERT_CHANNEL_ID = 1327548733398843413
ADMIN_ROLE_ID = 1280396795046006836
ROLE_TEST_ID = 1358771105980088390

BUTTONS = [
    ("WANTED", 1326671483455537172, "Def"),
    ("Attaque simultanée", 1326671483455537172, "Def"),
]

class PanelCog(commands.Cog):
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

        view = discord.ui.View()

        for label, role_id, embed_label in BUTTONS:
            btn = discord.ui.Button(
                label=label,
                emoji="🪳",
                style=discord.ButtonStyle.primary
                if label.lower() == "wanted"
                else discord.ButtonStyle.danger,
            )

            async def cb(
                i,
                label=label,
                role_id=role_id,
                embed_label=embed_label,
            ):
                cog = self.bot.get_cog("AlertsCog")
                await cog.send_alert(i, label, role_id, embed_label)

            btn.callback = cb
            view.add_item(btn)

        test_btn = discord.ui.Button(
            label="TEST",
            style=discord.ButtonStyle.secondary,
        )

        async def test_cb(i):
            if not any(r.id == ADMIN_ROLE_ID for r in i.user.roles):
                return await i.response.send_message(
                    "Admin only.",
                    ephemeral=True,
                )

            await i.response.send_message(
                "Alerte TEST envoyée.",
                ephemeral=True,
            )

            channel = i.guild.get_channel(ALERT_CHANNEL_ID)
            await channel.send(f"<@&{ROLE_TEST_ID}>")

        test_btn.callback = test_cb
        view.add_item(test_btn)

        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(PanelCog(bot))
