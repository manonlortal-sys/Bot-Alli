import asyncio
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands


LOG_CHANNEL_ID = 1445365655237955594  # Salon où envoyer les logs de suppressions
AUDIT_LOG_LOOKBACK_SECONDS = 10       # Fenêtre max entre la suppression et l'entrée d'audit


class MessageDeleteLogger(commands.Cog):
    """Cog qui log les messages supprimés par la modération (pas par l'auteur)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Événement déclenché quand un message est supprimé."""
        # Ignorer les DM
        if message.guild is None:
            return

        # Ignorer les messages des bots (optionnel, mais souvent utile)
        if message.author.bot:
            return

        # On récupère la guilde et le salon de logs
        guild = message.guild
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel is None:
            # Le salon n'existe pas sur cette guilde, on arrête
            return

        # On garde la date de suppression (approx = maintenant)
        deletion_time = datetime.now(timezone.utc)

        # Petite pause pour laisser le temps aux logs d'audit de se mettre à jour
        await asyncio.sleep(0.5)

        # On tente de trouver dans les logs d'audit QUI a supprimé le message
        deleter = await self._find_message_deleter(guild, message, deletion_time)

        # Si on n'a trouvé personne dans les logs d'audit :
        # - c'est très probablement l'auteur lui-même qui a supprimé
        # - ou un cas indétectable → on N'ARCHIVE PAS dans ton cas
        if deleter is None:
            return

        # À ce stade, on a identifié un "supprimeur" ≠ auteur → action de modération
        await self._send_log(log_channel, message, deleter, deletion_time)

    async def _find_message_deleter(
        self,
        guild: discord.Guild,
        message: discord.Message,
        deletion_time: datetime,
    ) -> discord.User | None:
        """
        Cherche dans les logs d'audit qui a supprimé ce message.

        Retourne:
            - l'utilisateur qui a supprimé le message (mod / bot de modération)
            - None si on ne trouve pas d'entrée cohérente (on considère alors que c'est l'auteur).
        """
        # Si le bot n'a pas la permission de voir les logs d'audit, on ne peut rien faire
        if not guild.me.guild_permissions.view_audit_log:
            return None

        # On limite le nombre d'entrées lues pour éviter les soucis de rate limit
        try:
            async for entry in guild.audit_logs(
                limit=10, action=discord.AuditLogAction.message_delete
            ):
                # entry.user  = celui qui a supprimé
                # entry.target = l'utilisateur dont le message a été supprimé

                # On ne s'intéresse qu'aux entrées concernant l'auteur du message
                if entry.target.id != message.author.id:
                    continue

                # Vérifier le salon si info dispo dans extra
                extra = entry.extra
                if hasattr(extra, "channel") and extra.channel.id != message.channel.id:
                    continue

                # Vérifier que l'entrée est récente (pour éviter les vieilles suppressions)
                if (
                    deletion_time - entry.created_at
                    > timedelta(seconds=AUDIT_LOG_LOOKBACK_SECONDS)
                ):
                    continue

                # Si on arrive là, on considère que cette entrée correspond à notre suppression
                return entry.user

        except discord.Forbidden:
            # Pas le droit de lire les logs d'audit
            return None
        except discord.HTTPException:
            # Problème API quelconque, on ne prend pas de risque
            return None

        # Rien trouvé de cohérent
        return None

    async def _send_log(
        self,
        log_channel: discord.TextChannel,
        message: discord.Message,
        deleter: discord.User,
        deletion_time: datetime,
    ):
        """Envoie un message d'archive dans le salon de logs."""

        # Formatage du contenu (on évite les messages trop longs)
        content = message.content if message.content else "*[aucun texte]*"
        if len(content) > 1024:
            content = content[:1000] + "\n...[tronqué]"

        # Date d'envoi du message
        sent_at = message.created_at.astimezone(timezone.utc)
        sent_at_str = sent_at.strftime("%d/%m/%Y à %H:%M:%S (UTC)")
        deletion_str = deletion_time.strftime("%d/%m/%Y à %H:%M:%S (UTC)")

        # Construction d'un embed pour que ce soit plus lisible
        embed = discord.Embed(
            title="🗑️ Message supprimé par la modération",
            color=discord.Color.red(),
            timestamp=deletion_time,
        )

        embed.add_field(
            name="Auteur du message",
            value=f"{message.author} (ID: {message.author.id})",
            inline=False,
        )

        embed.add_field(
            name="Supprimé par",
            value=f"{deleter} (ID: {deleter.id})",
            inline=False,
        )

        embed.add_field(
            name="Salon d'origine",
            value=f"{message.channel.mention} (ID: {message.channel.id})",
            inline=False,
        )

        embed.add_field(
            name="Envoyé le",
            value=sent_at_str,
            inline=True,
        )

        embed.add_field(
            name="Supprimé le",
            value=deletion_str,
            inline=True,
        )

        embed.add_field(
            name="Contenu",
            value=content,
            inline=False,
        )

        # Pièces jointes (si tu veux garder la trace des URLs)
        if message.attachments:
            attachments_text = "\n".join(att.url for att in message.attachments)
            if len(attachments_text) > 1024:
                attachments_text = attachments_text[:1000] + "\n...[tronqué]"
            embed.add_field(
                name="Pièces jointes",
                value=attachments_text,
                inline=False,
            )

        await log_channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MessageDeleteLogger(bot))
