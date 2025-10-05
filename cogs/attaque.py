# cogs/attaque.py
from typing import Optional, List, Tuple
import re
import discord
from discord.ext import commands
from discord import app_commands

from storage import insert_attack_report
from cogs.leaderboard import update_leaderboards

# Configuration
MAX_COOPS = 5
MAX_IMAGES = 3
ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")

MENTION_RE = re.compile(r"<@!?(\d+)>")

def _parse_coops(raw: Optional[str], guild: discord.Guild) -> Tuple[List[str], List[int]]:
    """
    Transforme une chaîne CSV (mentions/IDs/texte) en:
      - liste de mentions (str) pour affichage,
      - liste d'IDs (int) pour les compteurs.
    On garde max MAX_COOPS.
    """
    if not raw:
        return [], []
    mentions: List[str] = []
    ids: List[int] = []
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for p in parts:
        if len(ids) >= MAX_COOPS:
            break
        # <@123> / <@!123>
        m = MENTION_RE.fullmatch(p)
        if m:
            uid = int(m.group(1))
            mentions.append(f"<@{uid}>")
            ids.append(uid)
            continue
        # ID brut
        if p.isdigit():
            try:
                uid = int(p)
                _ = guild.get_member(uid) or None
                mentions.append(f"<@{uid}>")
                ids.append(uid)
                continue
            except Exception:
                pass
        # fallback: texte libre (affichage uniquement)
        mentions.append(p)
    return mentions[:MAX_COOPS], ids[:MAX_COOPS]


class AttaqueCog(commands.Cog):
    """Commande /attaque : coéquipiers (CSV opt), cible, et jusqu'à 3 screenshots attachés à la commande."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="attaque",
        description="Déclarer une attaque (coéquipiers, guilde/alliance attaquée, et 1–3 screens).",
    )
    @app_commands.describe(
        coequipiers="(optionnel) mentions/IDs séparés par des virgules : ex. '@A,@B,123' — max 5",
        cible="Nom de la guilde ou alliance attaquée",
        screenshot_1="Capture principale (image) — obligatoire",
        screenshot_2="Capture secondaire (image) — optionnel",
        screenshot_3="Capture tertiaire (image) — optionnel",
    )
    async def attaque(
        self,
        interaction: discord.Interaction,
        cible: str,
        screenshot_1: discord.Attachment,
        coequipiers: Optional[str] = None,
        screenshot_2: Optional[discord.Attachment] = None,
        screenshot_3: Optional[discord.Attachment] = None,
    ):
        """
        Publie l'alerte dans le même canal + enregistre le rapport pour le leaderboard Attaques.
        """
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Commande utilisable uniquement dans un serveur.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        # Coéquipiers (affichage + IDs pour compteurs)
        coop_mentions, coop_ids = _parse_coops(coequipiers, interaction.guild)

        # Collect attachments
        attachments: List[discord.Attachment] = []
        if screenshot_1:
            attachments.append(screenshot_1)
        if screenshot_2:
            attachments.append(screenshot_2)
        if screenshot_3:
            attachments.append(screenshot_3)

        # Validate attachments (images)
        image_urls: List[str] = []
        invalid_count = 0
        for att in attachments:
            if len(image_urls) >= MAX_IMAGES:
                break
            ok = False
            try:
                ctype = (att.content_type or "").lower()
                if ctype and ctype.startswith("image"):
                    ok = True
            except Exception:
                ok = False
            if not ok:
                fname = (att.filename or "").lower()
                if any(fname.endswith(ext) for ext in ALLOWED_EXT):
                    ok = True
            if ok:
                image_urls.append(att.url)
            else:
                invalid_count += 1

        if not image_urls:
            await interaction.followup.send(
                "⚠️ Aucune capture valide fournie. Attache au moins une image (png/jpg/webp).",
                ephemeral=True,
            )
            return

        # Build embed
        author = interaction.user
        title = f"⚔️ Attaque lancée par {author.display_name}"
        desc_lines: List[str] = []
        if coop_mentions:
            desc_lines.append(f"🧑‍🤝‍🧑 **Coéquipiers :** {', '.join(coop_mentions)}")
        else:
            desc_lines.append(f"🧑‍🤝‍🧑 **Coéquipiers :** —")
        cible_text = (cible or "").strip() or "—"
        desc_lines.append(f"🏰 **Guilde/Alliance attaquée :** {cible_text}")
        desc = "\n".join(desc_lines)

        embed = discord.Embed(title=title, description=desc, color=discord.Color.dark_red())
        embed.set_footer(text=f"Publié par {author.display_name}")

        try:
            embed.set_image(url=image_urls[0])
            if len(image_urls) > 1:
                others_lines = [f"[Capture {i}]({url})" for i, url in enumerate(image_urls[1:], start=2)]
                val = "\n".join(others_lines)
                if len(val) > 1024:
                    val = val[:1019] + "…"
                embed.add_field(name="📷 Autres captures", value=val, inline=False)
        except Exception:
            pass

        # Publish message
        try:
            sent = await interaction.channel.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Erreur lors de l'envoi de l'alerte : {e}", ephemeral=True)
            return

        # Enregistrer le rapport d'attaque (compte auteur + coéquipiers; cible si non vide)
        try:
            created_ts = int(sent.created_at.timestamp())
            target_for_db = (cible or "").strip()
            insert_attack_report(
                guild_id=interaction.guild.id,
                message_id=sent.id,
                author_id=author.id,
                coops=coop_ids,              # seuls les IDs valides sont comptés
                target=target_for_db if target_for_db else None,
                created_ts=created_ts,
            )
        except Exception:
            # on ne bloque pas la publication si l'insert échoue
            pass

        # MAJ des leaderboards (inclut le nouveau bloc Attaques)
        try:
            await update_leaderboards(self.bot, interaction.guild)
        except Exception:
            pass

        if invalid_count > 0:
            await interaction.followup.send(
                f"⚠️ {invalid_count} fichier(s) ignoré(s) (format non-image).",
                ephemeral=True,
            )

        await interaction.followup.send("✅ Alerte publiée.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AttaqueCog(bot))
