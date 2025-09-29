# cogs/pvp.py
from typing import List
import discord
from discord.ext import commands
from discord import app_commands

PVP_ROLE_ID = 1139552547737186334  # @pvp

# Mapping classes -> (label lisible, emoji custom rendu texte)
CLASS_EMOJIS = {
    "eniripsa": ("Eniripsa", "<:eni:1422183609154011146>"),
    "feca": ("Féca", "<:feca:1422183612169719878>"),
    "ecaflip": ("Ecaflip", "<:ecaflip:1422182948307865620>"),
    "pandawa": ("Pandawa", "<:panda:1422183617261600768>"),
    "zobal": ("Zobal", "<:zozo:1422183652141301880>"),
    "xelor": ("Xélor", "<:xel:1422183649851216025>"),
    "sadida": ("Sadida", "<:sadi:1422183636295487591>"),
    "enutrof": ("Enutrof", "<:enutrof:1422182952044859544>"),
    "osamodas": ("Osamodas", "<:osa:1422183613960687658>"),
    "sram": ("Sram", "<:sram:1422183638451355778>"),
    "iop": ("Iop", "<:iop:1422182955278925944>"),
    "sacrieur": ("Sacrieur", "<:sacri:1422183628720443496>"),
    "cra": ("Cra", "<:cra:1422183606301753395>"),
    "roublard": ("Roublard", "<:roub:1422183626531143781>"),
    "steamer": ("Steamer", "<:steam:1422183641030725642>"),
}

MODE_DISPLAY = {
    "kolizeum": "🏟️ Kolizeum 🏟️",
    "percepteur": "🐎 Percepteur 🐎",
}


class ClassesSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=lbl, value=key, description=None, emoji=None)
            for key, (lbl, _) in CLASS_EMOJIS.items()
        ]
        super().__init__(
            placeholder="Sélectionne une ou plusieurs classes…",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()  # on laisse le bouton gérer l'envoi


class ModeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Kolizeum", value="kolizeum", emoji="🏟️"),
            discord.SelectOption(label="Percepteur", value="percepteur", emoji="🐎"),
        ]
        super().__init__(
            placeholder="Choisis le mode (Kolizeum ou Percepteur)…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()  # on laisse le bouton gérer l'envoi


class PvPView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=180)
        self.author = author
        self.classes_select = ClassesSelect()
        self.mode_select = ModeSelect()
        self.add_item(self.classes_select)
        self.add_item(self.mode_select)

    @discord.ui.button(label="Envoyer l’alerte", style=discord.ButtonStyle.primary, emoji="⚔️")
    async def send_alert(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Seul l’initiateur peut envoyer cette alerte.", ephemeral=True)
            return

        selected_classes: List[str] = self.classes_select.values or []
        mode_vals: List[str] = self.mode_select.values or []

        if not selected_classes:
            await interaction.response.send_message("Sélectionne au moins **une classe**.", ephemeral=True)
            return
        if not mode_vals:
            await interaction.response.send_message("Sélectionne le **mode** (Kolizeum ou Percepteur).", ephemeral=True)
            return

        mode_key = mode_vals[0]
        mode_display = MODE_DISPLAY.get(mode_key, "Kolizeum")

        # Construire la liste en colonne avec emojis custom
        lines = []
        for key in selected_classes:
            label, emoji_txt = CLASS_EMOJIS.get(key, (key, ""))  # fallback
            lines.append(f"{emoji_txt} {label}")
        classes_block = "\n".join(lines)

        # Message hors embed : ping rôle PVP
        mention = f"<@&{PVP_ROLE_ID}>"

        # Embed bleu
        embed = discord.Embed(
            title="⚔️ ALERTE JOUEURS PVP ⚔️",
            description=(
                f"Le joueur **{self.author.display_name}** cherche les classes suivantes pour **{mode_display}** :\n\n"
                f"{classes_block}\n\n"
                f"*Merci de vous connecter ou de vous signaler auprès de ce joueur !*"
            ),
            color=discord.Color.blue(),
        )

        # Envoyer dans le même canal
        channel = interaction.channel
        await channel.send(mention)
        await channel.send(embed=embed)

        # Confirmer à l'utilisateur (éphémère)
        await interaction.response.send_message("✅ Alerte PVP envoyée.", ephemeral=True)
        self.stop()


class PvPCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pvp", description="Alerter @pvp avec les classes recherchées et le mode (Kolizeum/Percepteur).")
    async def pvp(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Commande à utiliser sur un serveur.", ephemeral=True)
            return

        view = PvPView(author=interaction.user)
        await interaction.response.send_message(
            "Configure ton alerte PVP ci-dessous, puis clique sur **Envoyer l’alerte**.",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(PvPCog(bot))
