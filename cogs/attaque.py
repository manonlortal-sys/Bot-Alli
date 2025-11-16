# cogs/attaque.py
import discord
from discord.ext import commands
from typing import Optional, Tuple

from storage import _load_logs, _save_logs
from cogs.alerts import update_attack_log_embed


class AttaqueCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ------------------------------
    # EXTRACTION INFO EMBED
    # ------------------------------
    @staticmethod
    def extract_attack_info(embed: discord.Embed) -> Tuple[Optional[str], Optional[str]]:
        """Retourne (team, alliance) depuis un embed d'alerte."""
        attacked = None
        attacker = None

        if embed.title and embed.title.startswith("🛡️ Alerte Attaque "):
            attacked = embed.title.replace("🛡️ Alerte Attaque ", "").strip()

        for f in embed.fields:
            if f.name == "État du combat":
                for line in f.value.splitlines():
                    if "⚔️ Attaquants :" in line:
                        attacker = line.split("⚔️ Attaquants :")[1].strip()
                        break

        return attacked, attacker

    # ------------------------------
    # MISE À JOUR JSON
    # ------------------------------
    async def update_attack_log_from_message(self, guild: discord.Guild, msg: discord.Message):
        if not msg.embeds:
            return

        attacked, attacker = self.extract_attack_info(msg.embeds[0])
        if not attacked:
            return

        data = _load_logs()
        logs = data.get(str(guild.id), [])

        for entry in logs:
            if entry["team"].lower() == attacked.lower():
                # mettre à jour seulement si non renseigné
                if attacker and not entry.get("attackers"):
                    entry["attackers"] = [attacker]
                break

        _save_logs(data)
        await update_attack_log_embed(self.bot, guild)

    # ------------------------------
    # LISTENERS
    # ------------------------------
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not after.guild or not after.embeds:
            return
        if not after.embeds[0].title or not after.embeds[0].title.startswith("🛡️ Alerte Attaque "):
            return
        await self.update_attack_log_from_message(after.guild, after)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or not message.embeds:
            return
        if not message.embeds[0].title or not message.embeds[0].title.startswith("🛡️ Alerte Attaque "):
            return
        await self.update_attack_log_from_message(message.guild, message)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or not message.embeds:
            return
        emb = message.embeds[0]
        if not emb.title or not emb.title.startswith("🛡️ Alerte Attaque "):
            return

        attacked, _ = self.extract_attack_info(emb)
        if not attacked:
            return

        data = _load_logs()
        logs = data.get(str(message.guild.id), [])
        logs = [l for l in logs if l["team"].lower() != attacked.lower()]
        data[str(message.guild.id)] = logs[:30]
        _save_logs(data)

        await update_attack_log_embed(self.bot, message.guild)


async def setup(bot):
    await bot.add_cog(AttaqueCog(bot))
