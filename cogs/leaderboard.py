# cogs/leaderboard.py

from __future__ import annotations

import discord
from discord.ext import commands
from typing import Dict, Set

# ⚠️ On lit l’état existant, on ne le modifie pas ici
from cogs.alerts import alerts_data

LEADERBOARD_CHANNEL_ID = 1459091766098788445
TOP_LIMIT = 20


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_id: int | None = None

    # -----------------------------
    # CALCUL DES STATS
    # -----------------------------
    def compute_stats(self):
        global_stats = {
            "attacks": 0,
            "wins": 0,
            "losses": 0,
            "incomplete": 0,
        }

        players: Dict[int, Dict[str, int]] = {}
        counted_incomplete_alerts: Set[int] = set()

        for alert_id, data in alerts_data.items():
            global_stats["attacks"] += 1

            if data["result"] == "win":
                global_stats["wins"] += 1
            elif data["result"] == "lose":
                global_stats["losses"] += 1

            if data["incomplete"]:
                global_stats["incomplete"] += 1
                counted_incomplete_alerts.add(alert_id)

            for uid in data["defenders"]:
                p = players.setdefault(
                    uid,
                    {"defenses": 0, "wins": 0, "losses": 0, "incomplete": 0},
                )

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

        # Classement par défenses
        sorted_players = sorted(
            players.items(),
            key=lambda x: x[1]["defenses"],
            reverse=True,
        )[:TOP_LIMIT]

        if not sorted_players:
            embed.add_field(
                name="🛡️ Défenseurs",
                value="_Aucune défense enregistrée._",
                inline=False,
            )
            return embed

        lines = []
        medals = ["🥇", "🥈", "🥉"]

        for idx, (uid, stats) in enumerate(sorted_players, start=1):
            medal = medals[idx - 1] if idx <= 3 else f"{idx}."
            lines.append(
                f"{medal} <@{uid}> — "
                f"🛡️ {stats['defenses']} | "
                f"🏆 {stats['wins']} | "
                f"❌ {stats['losses']} | "
                f"😡 {stats['incomplete']}"
            )

        embed.add_field(
            name=f"🛡️ Défenseurs (Top {TOP_LIMIT})",
            value="\n".join(lines),
            inline=False,
        )

        embed.set_footer(text="Mis à jour automatiquement • Temps réel")
        return embed

    # -----------------------------
    # MESSAGE MANAGEMENT
    # -----------------------------
    async def ensure_message(self):
        channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        if self.message_id:
            try:
                await channel.fetch_message(self.message_id)
                return
            except discord.HTTPException:
                self.message_id = None

        msg = await channel.send(embed=self.build_embed())
        self.message_id = msg.id

    async def refresh(self):
        channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        await self.ensure_message()
        if not self.message_id:
            return

        try:
            msg = await channel.fetch_message(self.message_id)
        except discord.HTTPException:
            self.message_id = None
            return

        await msg.edit(embed=self.build_embed())

    # -----------------------------
    # EVENTS
    # -----------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        await self.ensure_message()
        await self.refresh()

    # Hook léger : on refresh souvent, coût faible vu le volume
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.refresh()

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.refresh()


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))