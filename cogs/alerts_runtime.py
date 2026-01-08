# cogs/alerts_runtime.py

import discord
from discord.ext import commands

alerts_data = {}

class AlertsRuntimeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        emoji = str(reaction.emoji)
        msg = reaction.message

        data = alerts_data.setdefault(msg.id, {
            "defenders": set(),
            "result": None,
            "incomplete": False,
        })

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


async def setup(bot):
    await bot.add_cog(AlertsRuntimeCog(bot))
