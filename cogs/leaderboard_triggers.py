# cogs/leaderboard_triggers.py

from __future__ import annotations

import discord
from discord.ext import commands
from typing import Dict

from cogs.alerts import alerts_data

LEADERBOARD_CHANNEL_ID = 1459091766098788445
TOP_LIMIT = 20


class LeaderboardTriggers(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_id: int | None = None

    # -----------------------------
    # CALCUL DES STATS
    # -----------------------------
    def compute_ranking(self) -> Dict[int, int]:
        counts: Dict[int, int] = {}

        for data in alerts_data.values():
            uid = data["author"]
            counts[uid] = counts.get(uid, 0) + 1

        return counts

    # -----------------------------
    # BUILD EMBED
    # -----------------------------
    def build_embed(self) -> discord.Embed:
        counts = self.compute_ranking()

        embed = discord.Embed(
            title="🚨 Leaderboard Déclencheurs d’Alertes",
            description="Classement des joueurs ayant déclenché le plus d’alertes.",
            color=discord.Color.blurple(),
        )

        if not counts:
            embed.add_field(
                name="Classement",
                value="_Aucune alerte enregistrée._",
                inline=False,
            )
            embed.set_footer(text="Mis à jour automatiquement • Temps réel")
            return embed

        sorted_players = sorted(
            counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:TOP_LIMIT]

        medals = ["🥇", "🥈", "🥉"]
        lines = []

        for idx, (uid, count) in enumerate(sorted_players, start=1):
            prefix = medals[idx - 1] if idx <= 3 else f"{idx}."
            lines.append(f"{prefix} <@{uid}> — 🚨 {count}")

        embed.add_field(
            name=f"Classement (Top {TOP_LIMIT})",
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

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.refresh()

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.refresh()


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardTriggers(bot))