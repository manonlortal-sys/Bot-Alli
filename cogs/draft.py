import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import asyncio
import uuid
import os

TIMEOUT = 120
IMAGES_PATH = "draft_images"


# ============================================================
# SESSION DE DRAFT — STOCKE L’ÉTAT
# ============================================================
class DraftSession:
    def __init__(self, channel: discord.TextChannel):
        self.id = str(uuid.uuid4())

        self.channel = channel
        self.player_a: Optional[discord.Member] = None
        self.player_b: Optional[discord.Member] = None

        self.deck_a: list[str] = []
        self.deck_b: list[str] = []

        self.step = 0
        self.active = True

    def ready(self):
        return self.player_a and self.player_b


# ============================================================
# COG PRINCIPAL
# ============================================================
class Draft(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sessions: dict[str, DraftSession] = {}

    # --------------------------------------------------------
    # COMMANDE /draft
    # --------------------------------------------------------
    @app_commands.command(name="draft", description="Lancer une draft entre deux joueurs.")
    async def draft(self, interaction: discord.Interaction):
        session = DraftSession(interaction.channel)
        self.sessions[session.id] = session

        view = self.JoinView(self, session)

        await interaction.response.send_message(
            "🎯 **Draft en préparation**\n\n"
            "🔹 Joueur A : `?`\n"
            "🔸 Joueur B : `?`",
            view=view
        )

    # --------------------------------------------------------
    # LANCEMENT D’UNE ÉTAPE
    # --------------------------------------------------------
    async def send_step(self, session: DraftSession):
        session.step += 1
        step = session.step

        steps = {
            1: ("A", ["Xélor", "Eniripsa"], "etape1_xelor_eni.jpg"),
            2: ("B", ["Zobal", "Féca"], "etape2_zobal_feca.jpg"),
            3: ("A", ["Pandawa", "Sacrieur"], "etape3_pandawa_sacrieur.jpg"),
            4: ("B", ["Sadida", "Osamodas"], "etape4_osamodas_sadida.jpg"),
            5: ("A", ["Enutrof", "Steamer"], "etape5_enutrof_steamer.jpg"),
            6: ("B", ["Iop", "Ecaflip"], "etape6_ecaflip_iop.jpg"),
            7: ("A", ["Cra", "Sram", "Roublard"], "etape7_cra_sram_roublard.jpg"),
        }

        giver, choices, filename = steps[step]
        player = session.player_a if giver == "A" else session.player_b

        text = (
            f"🎯 **Étape {step} — Joueur {giver} ({player.mention})**\n"
            f"Choisis une classe : {', '.join(choices)}\n\n"
            "*(Image en dessous)*"
        )

        filepath = os.path.join(IMAGES_PATH, filename)
        file = discord.File(filepath) if os.path.exists(filepath) else None

        view = self.StepView(self, session, giver, choices)

        await session.channel.send(text, file=file, view=view)

    # --------------------------------------------------------
    # TRAITEMENT D’UN CHOIX
    # --------------------------------------------------------
    async def process_choice(self, session: DraftSession, giver: str, step: int, chosen: str):
        if not session.active:
            return

        if step <= 6:
            pairs = {
                1: ["Xélor", "Eniripsa"],
                2: ["Zobal", "Féca"],
                3: ["Pandawa", "Sacrieur"],
                4: ["Sadida", "Osamodas"],
                5: ["Enutrof", "Steamer"],
                6: ["Iop", "Ecaflip"],
            }

            other = [c for c in pairs[step] if c != chosen][0]

            if giver == "A":
                session.deck_a.append(chosen)
                session.deck_b.append(other)
            else:
                session.deck_b.append(chosen)
                session.deck_a.append(other)

        else:
            # Étape 7 : 1 choisi par A, 2 vont à B
            all3 = ["Cra", "Sram", "Roublard"]
            rest = [c for c in all3 if c != chosen]

            session.deck_a.append(chosen)
            session.deck_b.extend(rest)

        if step < 7:
            await self.send_step(session)
        else:
            await self.finish(session)

    # --------------------------------------------------------
    # FIN DE LA DRAFT
    # --------------------------------------------------------
    async def finish(self, session: DraftSession):
        session.active = False

        embed = discord.Embed(title="🎉 Résultat de la Draft", color=0xFFD700)

        embed.add_field(
            name=f"Deck de {session.player_a.display_name}",
            value="\n".join(f"- {c}" for c in session.deck_a),
            inline=False,
        )

        embed.add_field(
            name=f"Deck de {session.player_b.display_name}",
            value="\n".join(f"- {c}" for c in session.deck_b),
            inline=False,
        )

        await session.channel.send(embed=embed)
        del self.sessions[session.id]

    # ============================================================
    # VUES INTERNES — CORRECTES ET STABLES
    # ============================================================

    # ------------------------------------------------------------
    # VIEW DE JOIN
    # ------------------------------------------------------------
    class JoinView(discord.ui.View):
        def __init__(self, cog, session):
            super().__init__(timeout=TIMEOUT)
            self.cog = cog
            self.session = session

        async def on_timeout(self):
            if self.session.active and not self.session.ready():
                self.session.active = False
                await self.session.channel.send("⛔ Draft annulée (timeout).")

        @discord.ui.button(label="Joueur A", style=discord.ButtonStyle.primary)
        async def join_a(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.session.player_a is None:
                self.session.player_a = interaction.user
            else:
                return await interaction.response.send_message("Déjà pris.", ephemeral=True)

            await self.update(interaction)

        @discord.ui.button(label="Joueur B", style=discord.ButtonStyle.secondary)
        async def join_b(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.session.player_b is None:
                self.session.player_b = interaction.user
            else:
                return await interaction.response.send_message("Déjà pris.", ephemeral=True)

            await self.update(interaction)

        async def update(self, interaction):
            content = (
                "🎯 **Draft en préparation**\n\n"
                f"🔹 Joueur A : {self.session.player_a.mention if self.session.player_a else '`?`'}\n"
                f"🔸 Joueur B : {self.session.player_b.mention if self.session.player_b else '`?`'}"
            )

            await interaction.response.edit_message(content=content, view=self)

            if self.session.ready():
                for b in self.children:
                    b.disabled = True
                await self.session.channel.send("🚀 Début de la draft !")
                await self.cog.send_step(self.session)

    # ------------------------------------------------------------
    # VIEW D'ÉTAPE
    # ------------------------------------------------------------
    class StepView(discord.ui.View):
        def __init__(self, cog, session, giver, choices):
            super().__init__(timeout=TIMEOUT)
            self.cog = cog
            self.session = session
            self.giver = giver

            for c in choices:
                self.add_item(self.ChoiceButton(c, self))

            self.add_item(self.CancelButton(self))

        async def on_timeout(self):
            if self.session.active:
                self.session.active = False
                await self.session.channel.send("⛔ Draft annulée (inactivité).")

        # -------------------------
        # BOUTON DE CHOIX
        # -------------------------
        class ChoiceButton(discord.ui.Button):
            def __init__(self, label, parent):
                super().__init__(label=label, style=discord.ButtonStyle.secondary)
                self.parent = parent

            async def callback(self, interaction: discord.Interaction):
                expected = (
                    self.parent.session.player_a
                    if self.parent.giver == "A"
                    else self.parent.session.player_b
                )

                if interaction.user != expected:
                    return await interaction.response.send_message("Ce n’est pas ton tour.", ephemeral=True)

                await interaction.response.defer()
                await self.parent.cog.process_choice(
                    self.parent.session,
                    self.parent.giver,
                    self.parent.session.step,
                    self.label,
                )

        # -------------------------
        # BOUTON ANNULER
        # -------------------------
        class CancelButton(discord.ui.Button):
            def __init__(self, parent):
                super().__init__(label="Annuler", style=discord.ButtonStyle.danger)
                self.parent = parent

            async def callback(self, interaction: discord.Interaction):
                if interaction.user not in (self.parent.session.player_a, self.parent.session.player_b):
                    return await interaction.response.send_message("Seuls A ou B peuvent annuler.", ephemeral=True)

                self.parent.session.active = False
                await interaction.response.send_message("⛔ Draft annulée.")
                del self.parent.cog.sessions[self.parent.session.id]


# ============================================================
# AJOUT DU COG
# ============================================================
async def setup(bot):
    await bot.add_cog(Draft(bot))
