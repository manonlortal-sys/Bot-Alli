from __future__ import annotations
import discord
from discord.ext import commands
from typing import Dict
from cogs.alerts import alerts_data, DATA_PATH
import json
import os

LEADERBOARD_CHANNEL_ID = 1459091766098788445
TOP_LIMIT = 20
ADMIN_USER_ID = 1352575142668013588
ADMIN_ROLE_ID = 1280396795046006836


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------------
    # CALCUL DES STATS
    # -----------------------------
    def compute_stats(self):
        global_stats = {"attacks": 0, "wins": 0, "losses": 0, "incomplete": 0}
        players: Dict[int, Dict[str, int]] = {}

        for data in alerts_data.values():
            global_stats["attacks"] += 1
            if data["result"] == "win":
                global_stats["wins"] += 1
            elif data["result"] == "lose":
                global_stats["losses"] += 1
            if data["incomplete"]:
                global_stats["incomplete"] += 1

            for uid in data["defenders"]:
                p = players.setdefault(uid, {"defenses": 0, "wins": 0, "losses": 0, "incomplete": 0})
                p["defenses"] += 1
                if data["result"] == "win":
                    p["wins"] += 1
                elif data["result"] == "lose":
                    p["losses"] += 1
                if data["incomplete"]:
                    p["incomplete"] += 1

        return global_stats, players

    # -----------------------------
    # BUILD EMBED
    # -----------------------------
    def build_embed(self) -> discord.Embed:
        global_stats, players = self.compute_stats()
        embed = discord.Embed(
            title="📊 Leaderboard Défense Percepteurs",
            description="Statistiques mises à jour en temps réel.",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="🌍 Global",
            value=(
                f"⚔️ Attaques reçues : **{global_stats['attacks']}**\n"
                f"🏆 Victoires : **{global_stats['wins']}**\n"
                f"❌ Défaites : **{global_stats['losses']}**\n"
                f"😡 Défenses incomplètes : **{global_stats['incomplete']}**"
            ),
            inline=False,
        )

        sorted_players = sorted(players.items(), key=lambda x: x[1]["defenses"], reverse=True)[:TOP_LIMIT]

        if not sorted_players:
            embed.add_field(name="🛡️ Défenseurs", value="_Aucune défense enregistrée._", inline=False)
            return embed

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for idx, (uid, stats) in enumerate(sorted_players, start=1):
            prefix = medals[idx - 1] if idx <= 3 else f"{idx}."
            lines.append(f"{prefix} <@{uid}> — 🛡️ {stats['defenses']} | 🏆 {stats['wins']} | ❌ {stats['losses']} | 😡 {stats['incomplete']}")

        field_value = "\n".join(lines)
        if len(field_value) > 1024:
            field_value = field_value[:1021] + "…"

        embed.add_field(name=f"🛡️ Défenseurs (Top {TOP_LIMIT})", value=field_value, inline=False)
        embed.set_footer(text="Mis à jour automatiquement • Temps réel")
        return embed

    # -----------------------------
    # MESSAGE UNIQUE
    # -----------------------------
    async def get_or_create_message(self) -> discord.Message | None:
        channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return None

        async for msg in channel.history(limit=20):
            if msg.author.id == self.bot.user.id and msg.embeds:
                if msg.embeds[0].title == "📊 Leaderboard Défense Percepteurs":
                    return msg

        return await channel.send(embed=self.build_embed())

    async def refresh(self):
        msg = await self.get_or_create_message()
        if not msg:
            return
        await msg.edit(embed=self.build_embed())

    # -----------------------------
    # COMMANDES / SLASH
    # -----------------------------
    @discord.app_commands.command(
        name="reset",
        description="Réinitialise le leaderboard et les alertes (admin uniquement)"
    )
    async def reset(self, interaction: discord.Interaction):
        # Permissions : rôle admin ou ID
        has_admin_role = any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles)
        if interaction.user.id != ADMIN_USER_ID and not has_admin_role:
            await interaction.response.send_message("❌ Tu n'as pas la permission.", ephemeral=True)
            return

        # Vider les alertes en mémoire
        alerts_data.clear()

        # Réécrire le JSON vide
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)

        # Récupérer le salon leaderboard
        channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ Salon leaderboard introuvable.", ephemeral=True)
            return

        # Supprimer les anciens messages
        async for msg in channel.history(limit=50):
            if msg.author.id == self.bot.user.id and msg.embeds:
                if msg.embeds[0].title == "📊 Leaderboard Défense Percepteurs":
                    try:
                        await msg.delete()
                    except discord.HTTPException:
                        pass

        # Créer un nouveau message vide
        await channel.send(embed=self.build_embed())

        await interaction.response.send_message("✅ Leaderboard et alertes réinitialisés.", ephemeral=True)

    # -----------------------------
    # EVENTS
    # -----------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        await self.refresh()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.refresh()

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.refresh()


async def setup(bot: commands.Bot):
    cog = Leaderboard(bot)
    await bot.add_cog(cog)
    # Ajouter la commande slash au bot
    bot.tree.add_command(cog.reset)