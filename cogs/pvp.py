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
SPECIAL_ALL_EXCEPT_MINE = "ALL_EXCEPT_MINE"

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


# =========================
# SELECTS
# =========================
class MyClassesSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=lbl, value=key)
            for key, (lbl, _) in CLASS_EMOJIS.items()
        ]

        super().__init__(
            placeholder="🧙‍♂️ Sélectionne tes classes (j’ai déjà)…",
            min_values=1,
            max_values=min(len(options), 25),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class WantedClassesSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="✨ Toutes sauf les miennes",
                value=SPECIAL_ALL_EXCEPT_MINE,
                emoji="✨"
            ),
        ] + [
            discord.SelectOption(label=lbl, value=key)
            for key, (lbl, _) in CLASS_EMOJIS.items()
        ]

        super().__init__(
            placeholder="🎯 Sélectionne les classes recherchées…",
            min_values=1,
            max_values=min(len(options), 25),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class ModeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Kolizeum", value="kolizeum", emoji="🏟️"),
            discord.SelectOption(label="Percepteur", value="percepteur", emoji="🐎"),
        ]

        super().__init__(
            placeholder="Choisis le mode…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


# =========================
# MODAL
# =========================
class PvPNameModal(discord.ui.Modal):

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
        super().__init__(
            title="📝 Pseudo IG (optionnel)",
            timeout=300
        )

        self.author = author
        self.mine = mine
        self.wanted = wanted
        self.use_all_except = use_all_except
        self.mode_key = mode_key

    async def on_submit(self, interaction: discord.Interaction):

        mode_display = MODE_DISPLAY.get(self.mode_key, "Kolizeum")

        mine_block = render_classes_block(self.mine)

        wanted_block = (
            f"✨ Toutes sauf :\n{render_classes_block(self.mine)}"
            if self.use_all_except
            else render_classes_block(self.wanted)
        )

        pseudo_line = (
            f"👤 **Pseudo IG :** {str(self.pseudo).strip()}\n"
            if str(self.pseudo).strip()
            else ""
        )

        mention = f"<@&{PVP_ROLE_ID}>"

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

        await interaction.response.send_message(
            "✅ Alerte PVP envoyée.",
            ephemeral=True
        )


# =========================
# VIEW
# =========================
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

    @discord.ui.button(
        label="Envoyer l’alerte",
        style=discord.ButtonStyle.primary,
        emoji="⚔️"
    )
    async def send_alert(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if interaction.user.id != self.author.id:
            return await interaction.response.send_message(
                "Seul l’initiateur peut envoyer cette alerte.",
                ephemeral=True
            )

        mine: List[str] = self.my_classes.values or []
        wanted_vals: List[str] = self.wanted_classes.values or []
        mode_vals: List[str] = self.mode_select.values or []

        if not mine:
            return await interaction.response.send_message(
                "Sélectionne au moins une classe dans 'J’ai déjà'.",
                ephemeral=True
            )

        if not wanted_vals:
            return await interaction.response.send_message(
                "Sélectionne au moins une classe recherchée.",
                ephemeral=True
            )

        if not mode_vals:
            return await interaction.response.send_message(
                "Sélectionne un mode.",
                ephemeral=True
            )

        use_all_except = SPECIAL_ALL_EXCEPT_MINE in wanted_vals

        if use_all_except:
            mine_set: Set[str] = set(mine)
            wanted_set: Set[str] = set(ALL_KEYS) - mine_set

            wanted: List[str] = [
                k for k in ALL_KEYS if k in wanted_set
            ]

        else:
            wanted = [
                k for k in wanted_vals
                if k in CLASS_EMOJIS
            ]

        if not wanted:
            return await interaction.response.send_message(
                "Ta sélection exclut toutes les classes.",
                ephemeral=True
            )

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


# =========================
# COG
# =========================
class PvPCog(commands.Cog, name="PvP"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="pvp",
        description="Créer une alerte PVP"
    )
    async def pvp(self, interaction: discord.Interaction):

        guild = interaction.guild

        if guild is None:
            return await interaction.response.send_message(
                "Commande serveur uniquement.",
                ephemeral=True
            )

        view = PvPView(author=interaction.user)

        await interaction.response.send_message(
            "Configure ton alerte PVP puis clique sur 'Envoyer l’alerte'.",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(PvPCog(bot))
    print("✔ PvP cog chargé")