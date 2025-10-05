# cogs/attaque.py
from typing import Optional, List
import discord
from discord.ext import commands
from discord import app_commands

# Configuration
MAX_COOPS = 5
MAX_IMAGES = 3
ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")


class AttaqueCog(commands.Cog):
    """Commande /attaque : coéquipiers (CSV opt), cible, et jusqu'à 3 screenshots attachés à la commande."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="attaque",
        description="Déclarer une attaque (coéquipiers, guilde/alliance attaquée, et 1–3 screens).",
    )
    @app_commands.describe(
        coequipiers="(optionnel) mentions séparées par des virgules : ex. '@A,@B' — max 5",
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
        Flow :
         - l'utilisateur fournit la commande avec pièce(s) jointe(s) (attachments).
         - le bot valide les images, construit un embed et l'envoie dans le même canal.
        Notes :
         - Discord UI permet d'attacher des fichiers directement lors de l'exécution de la commande.
         - coequipiers est une chaîne optionnelle (CSV) car les slash options ne gèrent pas
           nativement un "multi user" paramètre dans toutes les versions.
        """

        # Vérifications basiques
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Commande utilisable uniquement dans un serveur.", ephemeral=True)
            return

        # Defer (si le traitement peut prendre >3s)
        await interaction.response.defer(ephemeral=False)

        # Parse coequipiers (CSV de mentions ou d'IDs) -> list of mention strings
        coop_mentions: List[str] = []
        if coequipiers:
            # split on comma, strip whitespace
            parts = [p.strip() for p in coequipiers.split(",") if p.strip()]
            for p in parts[:MAX_COOPS]:
                # accept either mention form <@id> or plain names; keep raw if ambiguous
                # try to convert to a Member mention if possible
                if p.startswith("<@") and p.endswith(">"):
                    coop_mentions.append(p)
                else:
                    # try resolve as member by name/id
                    member = None
                    try:
                        # try ID
                        if p.isdigit():
                            member = await interaction.guild.fetch_member(int(p))
                    except Exception:
                        member = None
                    if member:
                        coop_mentions.append(member.mention)
                    else:
                        # fallback: treat as plain text (will be shown as-is)
                        coop_mentions.append(p)

        # Collect attachments in order passed (1 is required)
        attachments: List[discord.Attachment] = []
        if screenshot_1:
            attachments.append(screenshot_1)
        if screenshot_2:
            attachments.append(screenshot_2)
        if screenshot_3:
            attachments.append(screenshot_3)

        # Validate attachments: keep only images, up to MAX_IMAGES
        image_urls: List[str] = []
        invalid_count = 0
        for att in attachments:
            if len(image_urls) >= MAX_IMAGES:
                break
            ok = False
            # prefer content_type check
            try:
                ctype = (att.content_type or "").lower()
                if ctype and ctype.startswith("image"):
                    ok = True
            except Exception:
                ok = False
            # fallback to filename ext
            if not ok:
                fname = (att.filename or "").lower()
                if any(fname.endswith(ext) for ext in ALLOWED_EXT):
                    ok = True
            if ok:
                # Use att.url (Discord-hosted) — reliable
                image_urls.append(att.url)
            else:
                invalid_count += 1

        # If first (required) is invalid or missing -> error
        if not image_urls:
            await interaction.followup.send(
                "⚠️ Aucune capture valide fournie. Assure-toi d'attacher au moins une image (png/jpg/webp).",
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
        desc_lines.append(f"🏰 **Guilde/Alliance attaquée :** {cible}")
        desc = "\n".join(desc_lines)

        embed = discord.Embed(title=title, description=desc, color=discord.Color.dark_red())
        embed.set_footer(text=f"Publié par {author.display_name}")

        # Attach images to embed: first as embed image, others as links field
        try:
            embed.set_image(url=image_urls[0])
            if len(image_urls) > 1:
                others_lines = []
                for i, url in enumerate(image_urls[1:], start=2):
                    others_lines.append(f"[Capture {i}]({url})")
                embed.add_field(name="📷 Autres captures", value="\n".join(others_lines), inline=False)
        except Exception:
            # fallback: ignore images if embed.set_image fails
            pass

        # If some attachments were invalid, inform the user (ephemeral)
        if invalid_count > 0:
            await interaction.followup.send(
                f"⚠️ {invalid_count} fichier(s) ignoré(s) (format non-image). Les images valides ont été publiées.",
                ephemeral=True,
            )

        # Send the embed in the same channel
        try:
            await interaction.channel.send(embed=embed)
        except Exception as e:
            # final fallback: notify author
            await interaction.followup.send(f"Erreur lors de l'envoi de l'alerte : {e}", ephemeral=True)
            return

        # Final ephemeral confirmation
        await interaction.followup.send("✅ Alerte publiée.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AttaqueCog(bot))
