# cogs/attaque.py
from typing import List, Optional
import discord
from discord.ext import commands
from discord import app_commands

MAX_COOP = 5
MAX_IMAGES = 3
THREAD_ARCHIVE_MINUTES = 60  # auto-archive duration in minutes


class AttackGuildModal(discord.ui.Modal, title="⚔️ Nom de l'alliance / guilde attaquée"):
    guild_name = discord.ui.TextInput(
        label="Nom de l’alliance ou de la guilde attaquée",
        placeholder="Ex : [Snowflake] ou Secteur K",
        required=True,
        max_length=120,
    )

    def __init__(self, author: discord.Member, coops: List[int], channel: discord.abc.GuildChannel):
        super().__init__(timeout=300)
        self.author = author
        self.coops = coops
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        # create thread in the channel where the command was invoked
        channel = self.channel
        if channel is None:
            await interaction.response.send_message("Impossible de récupérer le canal.", ephemeral=True)
            return

        thread_name = f"attaque-{self.author.display_name}"
        try:
            # create a public thread in the channel
            thread = await channel.create_thread(
                name=thread_name,
                auto_archive_duration=THREAD_ARCHIVE_MINUTES,
            )
        except Exception:
            # fallback: create thread from a starter message
            starter = await channel.send(f"Thread pour l'attaque de {self.author.mention}")
            thread = await starter.create_thread(name=thread_name, auto_archive_duration=THREAD_ARCHIVE_MINUTES)

        # initial instruction message in the thread + view with Publish button
        instr = (
            f"📎 **Poste ici jusqu'à {MAX_IMAGES} captures d'écran** (png/jpg/webp). "
            "Quand tu as fini, clique sur **Publier** pour que le bot poste l'alerte finale dans le canal."
        )
        view = PublishView(author=self.author, coops=self.coops, guild_name=self.guild_name.value, origin_channel=channel, origin_thread=thread)
        await thread.send(content=instr, view=view)

        # ack to user (ephemeral)
        await interaction.response.send_message(f"Thread créé : {thread.mention}. Postez vos captures dedans.", ephemeral=True)


class PublishView(discord.ui.View):
    def __init__(self, author: discord.Member, coops: List[int], guild_name: str, origin_channel: discord.abc.GuildChannel, origin_thread: discord.Thread):
        super().__init__(timeout=None)
        self.author = author
        self.coops = coops  # list of user IDs
        self.guild_name = guild_name
        self.origin_channel = origin_channel
        self.origin_thread = origin_thread

    @discord.ui.button(label="Publier", style=discord.ButtonStyle.success, emoji="📤")
    async def publish(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only allow in the thread where the view lives
        if interaction.channel is None or interaction.channel.id != self.origin_thread.id:
            await interaction.response.send_message("Ce bouton doit être utilisé dans le thread des captures.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # gather attachments from the thread messages (up to MAX_IMAGES)
        imgs = []
        try:
            async for m in self.origin_thread.history(limit=200):
                if m.attachments:
                    for att in m.attachments:
                        if len(imgs) >= MAX_IMAGES:
                            break
                        if att.content_type and att.content_type.startswith("image"):
                            imgs.append(att.url)
                        else:
                            # try to accept common extensions if content_type missing
                            lower = (att.filename or "").lower()
                            if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                                imgs.append(att.url)
                if len(imgs) >= MAX_IMAGES:
                    break
        except Exception:
            pass

        # build embed
        title = f"⚔️ Attaque lancée par {self.author.display_name}"
        desc_lines = []
        if self.coops:
            coop_mentions = ", ".join(f"<@{uid}>" for uid in self.coops)
            desc_lines.append(f"🧑‍🤝‍🧑 **Coéquipiers :** {coop_mentions}")
        desc_lines.append(f"🛡️ **Guilde/Alliance attaquée :** {self.guild_name}")
        desc = "\n".join(desc_lines)

        embed = discord.Embed(title=title, description=desc, color=discord.Color.dark_red())
        embed.set_footer(text=f"Publié par {self.author.display_name}")

        # send in origin channel (same channel as command)
        try:
            if imgs:
                files = []
                # Instead of downloading, we can attach images by URL in embed (set image for first, others as thumbnails are not supported)
                # Using URLs: set first as image, others as links in field
                embed.set_image(url=imgs[0])
                if len(imgs) > 1:
                    others = "\n".join(f"[Capture {i+1}]({url})" for i, url in enumerate(imgs[1:], start=1))
                    embed.add_field(name="📷 Autres captures", value=others, inline=False)
                await self.origin_channel.send(embed=embed)
            else:
                await self.origin_channel.send(embed=embed)
        except Exception:
            await interaction.followup.send("Erreur lors de l'envoi de l'alerte.", ephemeral=True)
            return

        # optionally archive/lock the thread (here we leave it)
        try:
            await self.origin_thread.edit(archived=True)
        except Exception:
            pass

        await interaction.followup.send("Alerte publiée.", ephemeral=True)


class CoopsSelectView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=300)
        self.author = author
        self.selected_ids: List[int] = []

        # add the user select element programmatically
        self.user_select = discord.ui.UserSelect(
            placeholder="Sélectionne tes coéquipiers (ou laisse vide)",
            min_values=0,
            max_values=MAX_COOP,
        )
        self.user_select.callback = self.on_select  # type: ignore
        self.add_item(self.user_select)

        # continue button
        self.add_item(self.ContinueButton())

    async def on_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        # store selected ids
        self.selected_ids = [u.id for u in select.values]
        # keep ephemeral ephemeral; do not respond here

    class ContinueButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Continuer", style=discord.ButtonStyle.primary)

        async def callback(self, interaction: discord.Interaction):
            view: CoopsSelectView = self.view  # type: ignore
            if view is None:
                await interaction.response.send_message("Erreur interne.", ephemeral=True)
                return
            # open modal to ask for guild name
            await interaction.response.send_modal(AttackGuildModal(author=interaction.user, coops=view.selected_ids, channel=interaction.channel))


class AttaqueCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="attaque", description="Déclarer une attaque : coéquipiers + guilde/alliance attaquée + screenshots")
    async def attaque(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None or interaction.channel is None:
            await interaction.response.send_message("Commande à utiliser sur un serveur.", ephemeral=True)
            return

        view = CoopsSelectView(author=interaction.user)
        await interaction.response.send_message("Sélectionne tes coéquipiers, puis clique sur Continuer.", view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AttaqueCog(bot))
