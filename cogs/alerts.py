from __future__ import annotations

import time
import discord
from discord.ext import commands
from discord import app_commands

# =============================
# CONFIG PAR SERVEUR
# =============================
GUILDS_CONFIG = {

    # =============================
    # SERVEUR 1
    # =============================
    1139550147190214727: {
        "ALERT_CHANNEL_ID": 1488527268287610964,
        "PANEL_CHANNEL_ID": None,

        "BUTTONS": [
            ("Wanted 1", "🗡️", discord.ButtonStyle.primary, "ROLE_WANTED_1"),
            ("Wanted 2", "🗡️", discord.ButtonStyle.primary, "ROLE_WANTED_2"),
            ("La peste", "🗡️", discord.ButtonStyle.primary, "ROLE_PESTE"),
            ("Lost Memory", "🗡️", discord.ButtonStyle.primary, "ROLE_LOST_MEMORY"),
            ("Rush", "🚨", discord.ButtonStyle.danger, "RUSH"),
            ("Test", "⚠️", discord.ButtonStyle.secondary, "ROLE_TEST"),
        ],

        "ROLES": {
            "ROLE_WANTED_1": 1419320456263237663,
            "ROLE_WANTED_2": 1421860260377006295,
            "ROLE_TEST": 1421867268421320844,
            "ROLE_PESTE": 1421927858967810110,
            "ROLE_LOST_MEMORY": 1519049947809321092,
        }
    },

    # =============================
    # SERVEUR 2
    # =============================
    1280234399610179634: {
        "ALERT_CHANNEL_ID": 1327548733398843413,
        "PANEL_CHANNEL_ID": 1358772372831994040,

        "BUTTONS": [
            ("Wanted", "⚔️", discord.ButtonStyle.primary, "ROLE_DEF"),
            ("Rush", "🚨", discord.ButtonStyle.danger, "RUSH"),
            ("Test", "⚠️", discord.ButtonStyle.secondary, "ROLE_TEST"),
        ],

        "ROLES": {
            "ROLE_DEF": 1326671483455537172,
            "ROLE_TEST": 1358771105980088390,
        }
    }
}

COOLDOWN = 30

last_ping = {}
alerts_data = {}


def get_config(guild_id):
    return GUILDS_CONFIG.get(guild_id)


def check_cd(key):
    now = time.time()
    if key in last_ping and now - last_ping[key] < COOLDOWN:
        return False
    last_ping[key] = now
    return True


# =============================
# ALERT VIEW
# =============================
class AlertView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Solo",
        style=discord.ButtonStyle.danger,
        custom_id="alert_solo"
    )
    async def solo_button(self, interaction: discord.Interaction, _):
        config = get_config(interaction.guild.id)

        alert_id = interaction.message.id
        alerts_data.pop(alert_id, None)

        try:
            await interaction.message.delete()
        except:
            pass

        if config:
            channel = interaction.guild.get_channel(
                config["ALERT_CHANNEL_ID"]
            )

            if channel:
                await channel.send(
                    f"⚠️ Alerte supprimée par **{interaction.user.display_name}** : "
                    f"il n’y a qu’un seul attaquant."
                )

        await interaction.response.defer()


# =============================
# COG
# =============================
class AlertsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.view = AlertView(bot)
        bot.add_view(self.view)

    def build_embed(self, data):
        color = discord.Color.blurple()

        if data["result"] == "win":
            color = discord.Color.green()
        elif data["result"] == "lose":
            color = discord.Color.red()

        state = "⏳ En cours"

        if data["result"] == "win":
            state = "🏆 Victoire"
        elif data["result"] == "lose":
            state = "❌ Défaite"

        embed = discord.Embed(
            title="⚠️ Percepteur attaqué",
            description="🗡️ Un percepteur est en cours d’attaque !",
            color=color
        )

        embed.add_field(
            name="🔔 Déclenché par",
            value=f"<@{data['author']}>",
            inline=False
        )

        embed.add_field(
            name="📊 État de l’attaque",
            value=state,
            inline=False
        )

        embed.set_footer(
            text="🏆 victoire • ❌ défaite"
        )

        return embed

    async def update_msg(self, message_id):
        data = alerts_data.get(message_id)

        if not data:
            return

        channel = self.bot.get_channel(
            data["channel_id"]
        )

        msg = await channel.fetch_message(
            message_id
        )

        await msg.edit(
            embed=self.build_embed(data),
            view=self.view
        )

    # =============================
    # API RÉACTIONS
    # =============================
    async def mark_defense_won(self, alert_id):
        if alert_id in alerts_data:
            alerts_data[alert_id]["result"] = "win"
            await self.update_msg(alert_id)

    async def mark_defense_lost(self, alert_id):
        if alert_id in alerts_data:
            alerts_data[alert_id]["result"] = "lose"
            await self.update_msg(alert_id)

    # =============================
    # ALERTE CLASSIQUE
    # =============================
    async def send_alert(self, interaction, role_id):
        config = get_config(interaction.guild.id)

        if not config:
            return

        if not check_cd(role_id):
            return await interaction.response.send_message(
                "Cooldown",
                ephemeral=True
            )

        channel = interaction.guild.get_channel(
            config["ALERT_CHANNEL_ID"]
        )

        await interaction.response.send_message(
            "Alerte envoyée",
            ephemeral=True
        )

        await channel.send(
            f"<@&{role_id}>"
        )

        data = {
            "author": interaction.user.id,
            "result": None,
            "channel_id": channel.id
        }

        msg = await channel.send(
            embed=self.build_embed(data),
            view=self.view
        )

        alerts_data[msg.id] = data

        for e in ("🏆", "❌"):
            await msg.add_reaction(e)

    # =============================
    # RUSH
    # =============================
    async def send_rush(self, interaction):
        config = get_config(interaction.guild.id)

        if not config:
            return

        if not check_cd("RUSH"):
            return await interaction.response.send_message(
                "Cooldown",
                ephemeral=True
            )

        channel = interaction.guild.get_channel(
            config["ALERT_CHANNEL_ID"]
        )

        await interaction.response.send_message(
            "Rush envoyé",
            ephemeral=True
        )

        await channel.send(
            "@everyone"
        )

        data = {
            "author": interaction.user.id,
            "result": None,
            "channel_id": channel.id
        }

        msg = await channel.send(
            embed=self.build_embed(data),
            view=self.view
        )

        alerts_data[msg.id] = data

        for e in ("🏆", "❌"):
            await msg.add_reaction(e)

    # =============================
    # TEST
    # =============================
    async def send_test(self, interaction):
        config = get_config(interaction.guild.id)

        channel = interaction.guild.get_channel(
            config["ALERT_CHANNEL_ID"]
        )

        await interaction.response.send_message(
            "Test envoyé",
            ephemeral=True
        )

        await channel.send(
            f"<@&{config['ROLES']['ROLE_TEST']}>"
        )

        data = {
            "author": interaction.user.id,
            "result": None,
            "channel_id": channel.id
        }

        msg = await channel.send(
            embed=self.build_embed(data),
            view=self.view
        )

        alerts_data[msg.id] = data

        for e in ("🏆", "❌"):
            await msg.add_reaction(e)

    # =============================
    # PANEL
    # =============================
    @app_commands.command(
        name="pingpanel",
        description="Panel alertes"
    )
    async def pingpanel(
        self,
        interaction: discord.Interaction
    ):
        config = get_config(
            interaction.guild.id
        )

        if not config:
            return await interaction.response.send_message(
                "Serveur non configuré.",
                ephemeral=True
            )

        if (
            config["PANEL_CHANNEL_ID"]
            and interaction.channel.id != config["PANEL_CHANNEL_ID"]
        ):
            return await interaction.response.send_message(
                "Commande interdite ici.",
                ephemeral=True
            )

        view = discord.ui.View(
            timeout=None
        )

        for label, emoji, style, action in config["BUTTONS"]:

            async def callback(
                i,
                action=action
            ):
                if action == "RUSH":
                    await self.send_rush(i)

                else:
                    role_id = config["ROLES"][action]
                    await self.send_alert(
                        i,
                        role_id
                    )

            b = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=style
            )

            b.callback = callback

            view.add_item(b)

        await interaction.response.send_message(
            "⚔️ Panel de défense percepteurs\n"
            "Clique sur un bouton pour envoyer une alerte.",
            view=view
        )


async def setup(bot):
    await bot.add_cog(
        AlertsCog(bot)
    )