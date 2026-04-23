import discord
from discord.ext import commands
from cogs.alerts import alerts_data


class Reactions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id is None:
            return
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id not in alerts_data:
            return

        cog = self.bot.get_cog("AlertsCog")
        if not cog:
            return

        emoji = str(payload.emoji)

        if emoji == "👍":
            await cog.add_defender_to_alert(payload.message_id, payload.user_id)
        elif emoji == "🏆":
            await cog.mark_defense_won(payload.message_id)
        elif emoji == "❌":
            await cog.mark_defense_lost(payload.message_id)
        elif emoji == "😡":
            await cog.toggle_incomplete(payload.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.guild_id is None:
            return
        if payload.message_id not in alerts_data:
            return

        cog = self.bot.get_cog("AlertsCog")
        if not cog:
            return

        if str(payload.emoji) == "👍":
            await cog.remove_defender_from_alert(payload.message_id, payload.user_id)


async def setup(bot):
    await bot.add_cog(Reactions(bot))