# cogs/attaque.py
from typing import Optional, List, Tuple
import discord
from discord.ext import commands

from storage import (
    _load_logs,
    _save_logs,
)
from cogs.leaderboard import update_leaderboards

# ID du canal où se trouve l’historique
SNAPSHOT_CHANNEL_ID = 1421866144679329984
MAX_ATTACKS = 30


class AttaqueCog(commands.Cog):
    """Mise à jour automatique du message d’historique des attaques percepteurs avec la guilde attaquante et l’alliance."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------- Extraction des infos depuis un embed --------
    @staticmethod
    def extract_attack_info(embed: discord.Embed) -> Tuple[Optional[str], Optional[str]]:
        """Récupère la guilde attaquée et l'alliance attaquante depuis l'embed d'une alerte."""
        attacked = None
        attacker = None

        if embed.title and embed.title.startswith("🛡️ Alerte Attaque "):
            attacked = embed.title.replace("🛡️ Alerte Attaque ", "").strip()

        for field in embed.fields:
            if field.name == "État du combat" and "⚔️ Attaquants :" in field.value:
                for line in field.value.splitlines():
                    if line.strip().startswith("⚔️ Attaquants :"):
                        attacker = line.split("⚔️ Attaquants :")[1].strip()
                        break
        return attacked, attacker

    # -------- Mise à jour de l’historique local --------
    async def update_attack_log_from_message(self, guild: discord.Guild, msg: discord.Message):
        """Met à jour storage_attack_log.json avec l'alliance attaquante récupérée depuis le message."""
        if not msg.embeds:
            return

        embed = msg.embeds[0]
        attacked, attacker = self.extract_attack_info(embed)
        if not attacked:
            return

        data = _load_logs()
        logs = data.get(str(guild.id), [])

        # Trouver la ligne correspondante à la guilde attaquée la plus récente
        for entry in logs:
            if entry["team"].lower() == attacked.lower() and entry.get("attackers", "—") == "—":
                if attacker:
                    entry["attackers"] = attacker
                    break

        _save_logs(data)
        await self.update_attack_log_embed(guild)

    # -------- Réécriture de l’embed d’historique --------
    async def update_attack_log_embed(self, guild: discord.Guild):
        """Met à jour l’embed d’historique des attaques dans le canal dédié."""
        channel = guild.get_channel(SNAPSHOT_CHANNEL_ID)
        if not channel:
            return

        data = _load_logs()
        logs = data.get(str(guild.id), [])

        if not logs:
            desc = "_Aucune attaque enregistrée._"
        else:
            desc = "\n".join(
                f"• **{log['team']}** attaquée à <t:{log['time']}:t> par `{log.get('attackers', '—')}`"
                for log in logs
            )

        embed = discord.Embed(
            title="📜 Historique des attaques percepteurs",
            description=desc,
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Dernières {MAX_ATTACKS} attaques")

        async for msg in channel.history(limit=20):
            if msg.author == self.bot.user and msg.embeds:
                try:
                    await msg.edit(embed=embed)
                    return
                except discord.HTTPException:
                    break
        await channel.send(embed=embed)

    # -------- Événements de mise à jour d’alerte --------
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Quand une alerte est mise à jour (ex: ajout d'attaquants), on actualise l’historique."""
        if not after.guild or not after.embeds:
            return
        # Vérifie que c'est bien une alerte percepteur (embed d'alerte)
        emb = after.embeds[0]
        if not emb.title or not emb.title.startswith("🛡️ Alerte Attaque "):
            return
        await self.update_attack_log_from_message(after.guild, after)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Quand une nouvelle alerte est envoyée, on vérifie si elle contient déjà un attaquant."""
        if not message.guild or not message.embeds:
            return
        emb = message.embeds[0]
        if not emb.title or not emb.title.startswith("🛡️ Alerte Attaque "):
            return
        await self.update_attack_log_from_message(message.guild, message)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Supprime une entrée d’historique si une alerte est supprimée."""
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
        data[str(message.guild.id)] = logs[:MAX_ATTACKS]
        _save_logs(data)
        await self.update_attack_log_embed(message.guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(AttaqueCog(bot))
