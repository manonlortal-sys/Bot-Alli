# cogs/pvp.py
from typing import List, Set
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

ALL_KEYS: List[str] = list(CLASS_EMOJIS.keys())
SPECIAL_ALL_EXCEPT_MINE = "ALL_EXCEPT_MINE"  # valeur spéciale du sélecteur "recherchées"

MODE_DISPLAY = {
    "kolizeum": "🏟️ Kolizeum 🏟️",
    "percepteur": "🐎 Percepteur 🐎",
}


def render_classes_block(keys: List[str]) -> str:
    lines: List[str] = []
    for k in keys:
        label, emoji_txt = CLASS_EMOJIS.get(k, (k, ""))
        lines.append(f"{emoji_txt} {label}")
    return "\n".join(lines) if lines else "—"


class MyClassesSelect(discord.ui.Select):
    """Sélecteur multi pour les classes que le joueur a (aucune limite max)."""
    def __init__(self):
        options = [
            discord.SelectOption(label=lbl, value=key)
            for key, (lbl, _) in CLASS_EMOJIS.items()
        ]
        super().__init__(
            placeholder="🧙‍♂️ Sélectionne **tes classes** (j’ai déjà)…",
            min_values=1,
            max_values=len(options),  # pas de limite
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()  # le bouton gère la suite


class WantedClassesSelect(discord.ui.Select):
    """Sélecteur multi pour les classes recherchées + option ✨ Toutes sauf les miennes."""
    def __init__(self):
        options = [
            discord.SelectOption(label="✨ Toutes sauf les miennes", value=SPECIAL_ALL_EXCEPT_MINE, emoji="✨"),
        ] + [
            discord.SelectOption(label=lbl, value=key)
            for key, (lbl, _) in CLASS_EMOJIS.items()
        ]
        super().__init__(
            placeholder="🎯 Sélectionne les **classes recherchées**… (ou ✨ Toutes sauf les miennes)",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()  # le bouton gère la suite


class ModeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Kolizeum", value="kolizeum", emoji="🏟️"),
            discord.SelectOption(label="Percepteur", value="percepteur", emoji="🐎"),
        ]
        super().__init__(
            placeholder="Choisis le **mode** (Kolizeum ou Percepteur)…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class PvPNameModal(discord.ui.Modal, title="📝 Pseudo IG (optionnel)"):
    pseudo = discord.ui.TextInput(
        label="Ton pseudo en jeu (optionnel)",
        placeholder="Ex: Kicard",
        required=False,
        max_length=64,
    )

    def __init__(
        self,
        author: discord.Member,
        mine: List[str],
        wanted: List[str],
        use_all_except: bool,
        mode_key: str,
    ):
        super().__init__(timeout=300)
        self.author = author
        self.mine = mine
        self.wanted = wanted
        self.use_all_except = use_all_except
        self.mode_key = mode_key

    async def on_submit(self, interaction: discord.Interaction):
        mode_display = MODE_DISPLAY.get(self.mode_key, "Kolizeum")

        # Rendu blocs
        mine_block = render_classes_block(self.mine)
        wanted_block = (
            f"✨ Toutes sauf :\n{render_classes_block(self.mine)}"
            if self.use_all_except else
            render_classes_block(self.wanted)
        )

        # Section pseudo (si rempli)
        pseudo_line = f"👤 **Pseudo IG :** {str(self.pseudo).strip()}\n" if str(self.pseudo).strip() else ""

        # Ping hors embed
        mention = f"<@&{PVP_ROLE_ID}>"

        # Embed
        embed = discord.Embed(
            title="⚔️ ALERTE JOUEURS PVP ⚔️",
            description=(
                f"{pseudo_line}"
                f"Le joueur **{self.author.display_name}** cherche du monde pour **{mode_display}**.\n\n"
                f"🧙‍♂️ **J’ai déjà :**\n{mine_block}\n\n"
                f"🎯 **Je recherche :**\n{wanted_block}\n\n"
                f"*Merci de vous connecter ou de vous signaler auprès de ce joueur !*"
            ),
            color=discord.Color.blue(),
        )

        channel = interaction.channel
        await channel.send(mention)
        await channel.send(embed=embed)

        await interaction.response.send_message("✅ Alerte PVP envoyée.", ephemeral=True)


class PvPView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=180)
        self.author = author
        self.my_classes = MyClassesSelect()
        self.wanted_classes = WantedClassesSelect()
        self.mode_select = ModeSelect()
        self.add_item(self.my_classes)
        self.add_item(self.wanted_classes)
        self.add_item(self.mode_select)

    @discord.ui.button(label="Envoyer l’alerte", style=discord.ButtonStyle.primary, emoji="⚔️")
    async def send_alert(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Seul l’initiateur peut envoyer cette alerte.", ephemeral=True)
            return

        mine: List[str] = self.my_classes.values or []
        wanted_vals: List[str] = self.wanted_classes.values or []
        mode_vals: List[str] = self.mode_select.values or []

        # Validations
        if not mine:
            await interaction.response.send_message("Sélectionne au moins **une classe** dans **J’ai déjà**.", ephemeral=True)
            return
        if not wanted_vals:
            await interaction.response.send_message("Sélectionne au moins **une** classe dans **Je recherche** (ou ✨ Toutes sauf les miennes).", ephemeral=True)
            return
        if not mode_vals:
            await interaction.response.send_message("Sélectionne le **mode** (Kolizeum ou Percepteur).", ephemeral=True)
            return

        # Logique "Toutes sauf les miennes"
        use_all_except = SPECIAL_ALL_EXCEPT_MINE in wanted_vals
        if use_all_except:
            mine_set: Set[str] = set(mine)
            wanted_set: Set[str] = set(ALL_KEYS) - mine_set
            wanted: List[str] = [k for k in ALL_KEYS if k in wanted_set]  # conserver l’ordre global
        else:
            wanted = [k for k in wanted_vals if k in CLASS_EMOJIS]

        if not wanted:
            await interaction.response.send_message("Ta sélection **exclut toutes les classes**. Ajuste tes choix.", ephemeral=True)
            return

        # Ouvrir le modal pour demander (optionnel) le pseudo IG
        mode_key = mode_vals[0]
        await interaction.response.send_modal(
            PvPNameModal(
                author=self.author,
                mine=mine,
                wanted=wanted,
                use_all_except=use_all_except,
                mode_key=mode_key,
            )
        )
        self.stop()


class PvPCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pvp", description="Alerter @pvp avec tes classes et celles que tu recherches (Kolizeum/Percepteur).")
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
