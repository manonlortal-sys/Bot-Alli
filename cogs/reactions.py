# cogs/reactions.py

import discord
from discord.ext import commands

from cogs.alerts import alerts_data


class Reactions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id not in alerts_data:
            return

        alerts_cog = self.bot.get_cog("AlertsCog")
        if not alerts_cog:
            return

        emoji = str(payload.emoji)

        if emoji == "👍":
            await alerts_cog.add_defender(payload.message_id, payload.user_id)
        elif emoji == "🏆":
            await alerts_cog.set_result(payload.message_id, "win")
        elif emoji == "❌":
            await alerts_cog.set_result(payload.message_id, "lose")
        elif emoji == "😡":
            await alerts_cog.toggle_incomplete(payload.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        if payload.message_id not in alerts_data:
            return

        alerts_cog = self.bot.get_cog("AlertsCog")
        if not alerts_cog:
            return

        emoji = str(payload.emoji)

        if emoji == "👍":
            await alerts_cog.remove_defender(payload.message_id, payload.user_id)
        elif emoji in ("🏆", "❌"):
            await alerts_cog.clear_result(payload.message_id)
        elif emoji == "😡":
            await alerts_cog.clear_incomplete(payload.message_id)


async def setup(bot):
    await bot.add_cog(Reactions(bot))
