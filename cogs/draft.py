import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import uuid
import os
from typing import Optional  # ✔ indispensable pour Python 3.9


IMAGES_PATH = "draft_images"
TIMEOUT = 120  # secondes


# ------------------------------------------------------------
# Structure représentant une draft active
# ------------------------------------------------------------
class DraftSession:
    def __init__(self, channel: discord.TextChannel, starter_id: int):
        self.id = str(uuid.uuid4())  # identifiant unique de la draft
        self.channel = channel
        self.starter_id = starter_id

        # ✔ Compatibilité Python 3.9
        self.player_a: Optional[discord.Member] = None
        self.player_b: Optional[discord.Member] = None

        self.deck_a: list[str] = []
        self.deck_b: list[str] = []

        self.current_step = 0
        self.active = True

        # ✔ Compatibilité Python 3.9
        self.last_message: Optional[discord.Message] = None

    def is_ready(self):
        return self.player_a is not None and self.player_b is not None


# ------------------------------------------------------------
# Boutons A/B pour s'inscrire
# ------------------------------------------------------------
class JoinButton(discord.ui.Button):
    def __init__(self, label, role):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.role = role  # "A" ou "B"

    async def callback(self, interaction: discord.Interaction):
        view: DraftJoinView = self.view
        session = view.session

        if not session.active:
            return await interaction.response.send_message(
                "Cette draft est déjà terminée.", ephemeral=True
            )

        user = interaction.user

        # empêcher qu'un joueur prenne A et B
        if session.player_a == user or session.player_b == user:
            return await interaction.response.send_message(
                "Tu es déjà inscrit dans cette draft.", ephemeral=True
            )

        # affectation du joueur
        if self.role == "A" and session.player_a is None:
            session.player_a = user
        elif self.role == "B" and session.player_b is None:
            session.player_b = user
        else:
            return await interaction.response.send_message(
                "Ce rôle est déjà pris.", ephemeral=True
            )

        # mise à jour du message d'inscription
        txt = f"🎯 **Draft en préparation**\n\n"
        txt += f"🔹 Joueur A : {session.player_a.mention if session.player_a else '`?`'}\n"
        txt += f"🔸 Joueur B : {session.player_b.mention if session.player_b else '`?`'}\n"

        await interaction.response.edit_message(content=txt, view=view)

        # si A et B sont prêts → démarrer la draft
        if session.is_ready():
            await asyncio.sleep(1)
            await view.start_draft()


class DraftJoinView(discord.ui.View):
    def __init__(self, session: DraftSession, cog):
        super().__init__(timeout=TIMEOUT)
        self.session = session
        self.cog = cog

        self.add_item(JoinButton("Joueur A", "A"))
        self.add_item(JoinButton("Joueur B", "B"))
        self.add_item(CancelButton(session, cog))

    async def on_timeout(self):
        if self.session.active:
            self.session.active = False
            await self.session.channel.send("⛔ Draft annulée (temps écoulé).")

    async def start_draft(self):
        # enlever les boutons
        for child in self.children:
            child.disabled = True

        await self.session.channel.send("🚀 La draft commence !")
        await self.cog.send_step(self.session, 1)


# ------------------------------------------------------------
# Bouton Annuler
# ------------------------------------------------------------
class CancelButton(discord.ui.Button):
    def __init__(self, session, cog):
        super().__init__(label="Annuler", style=discord.ButtonStyle.danger)
        self.session = session
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user

        if user != self.session.player_a and user != self.session.player_b:
            return await interaction.response.send_message(
                "Seuls les joueurs A ou B peuvent annuler.", ephemeral=True
            )

        self.session.active = False
        await interaction.response.send_message("⛔ Draft annulée.")
        self.cog.end_session(self.session.id)


# ------------------------------------------------------------
# Boutons de choix de classe
# ------------------------------------------------------------
class ClassChoiceButton(discord.ui.Button):
    def __init__(self, label, step, cog, session, giver):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.label_class = label
        self.step = step
        self.cog = cog
        self.session = session
        self.giver = giver  # "A" ou "B"

    async def callback(self, interaction: discord.Interaction):
        session = self.session
        user = interaction.user

        # vérifier le tour
        expected = session.player_a if self.giver == "A" else session.player_b
        if user != expected:
            return await interaction.response.send_message(
                "Ce n'est pas ton tour.", ephemeral=True
            )

        await interaction.response.defer()

        await self.cog.process_choice(session, self.step, self.label_class)


class ClassChoiceView(discord.ui.View):
    def __init__(self, session, cog, step, giver, choices):
        super().__init__(timeout=TIMEOUT)
        self.session = session
        self.cog = cog

        for c in choices:
            self.add_item(ClassChoiceButton(c, step, cog, session, giver))

        self.add_item(CancelButton(session, cog))

    async def on_timeout(self):
        if self.session.active:
            self.session.active = False
            await self.session.channel.send("⛔ Draft annulée (inactivité).")


# ------------------------------------------------------------
# COG PRINCIPAL
# ------------------------------------------------------------
class Draft(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sessions: dict[str, DraftSession] = {}

    # --------------------------------------------------------
    # Commande /draft
    # --------------------------------------------------------
    @app_commands.command(name="draft", description="Lancer une draft entre deux joueurs.")
    async def draft(self, interaction: discord.Interaction):
        session = DraftSession(interaction.channel, interaction.user.id)
        self.sessions[session.id] = session

        view = DraftJoinView(session, self)

        msg = await interaction.response.send_message(
            f"🎯 **Draft en préparation**\n\n"
            f"🔹 Joueur A : `?`\n"
            f"🔸 Joueur B : `?`",
            view=view
        )

        session.last_message = await interaction.original_response()

    # --------------------------------------------------------
    # Envoi d'une étape
    # --------------------------------------------------------
    async def send_step(self, session: DraftSession, step: int):
        session.current_step = step

        steps = {
            1: ("A", ["Xélor", "Eniripsa"], "etape1_xelor_eni.jpg"),
            2: ("B", ["Zobal", "Féca"], "etape2_zobal_feca.jpg"),
            3: ("A", ["Pandawa", "Sacrieur"], "etape3_pandawa_sacrieur.jpg"),
            4: ("B", ["Sadida", "Osamodas"], "etape4_osamodas_sadida.jpg"),
            5: ("A", ["Enutrof", "Steamer"], "etape5_enutrof_steamer.jpg"),
            6: ("B", ["Iop", "Ecaflip"], "etape6_ecaflip_iop.jpg"),
            7: ("A", ["Cra", "Sram", "Roublard"], "etape7_cra_sram_roublard.jpg"),
        }

        giver, choices, img = steps[step]

        player = session.player_a if giver == "A" else session.player_b

        text = (
            f"🎯 **Étape {step} — Choix du joueur {giver} ({player.mention})**\n"
            f"Choisis une classe : {', '.join(choices)}\n\n"
            f"*(L'image est juste en dessous)*"
        )

        filepath = os.path.join(IMAGES_PATH, img)
        file = discord.File(filepath)

        view = ClassChoiceView(session, self, step, giver, choices)

        msg = await session.channel.send(text, file=file, view=view)
        session.last_message = msg

    # --------------------------------------------------------
    # Traitement d'un choix
    # --------------------------------------------------------
    async def process_choice(self, session: DraftSession, step: int, chosen: str):
        if not session.active:
            return

        # Règles de distribution
        pairs = {
            1: ["Xélor", "Eniripsa"],
            2: ["Zobal", "Féca"],
            3: ["Pandawa", "Sacrieur"],
            4: ["Sadida", "Osamodas"],
            5: ["Enutrof", "Steamer"],
            6: ["Iop", "Ecaflip"],
        }

        if step <= 6:
            other = [c for c in pairs[step] if c != chosen][0]

            giver = "A" if step in [1, 3, 5] else "B"
            taker = "B" if giver == "A" else "A"

            if giver == "A":
                session.deck_a.append(chosen)
                session.deck_b.append(other)
            else:
                session.deck_b.append(chosen)
                session.deck_a.append(other)

        else:
            # étape 7 : 1 choisi pour A, 2 pour B
            all3 = ["Cra", "Sram", "Roublard"]
            rest = [c for c in all3 if c != chosen]
            session.deck_a.append(chosen)
            session.deck_b.extend(rest)

        # avancer
        if step < 7:
            await self.send_step(session, step + 1)
        else:
            await self.finish_draft(session)

    # --------------------------------------------------------
    # Fin de draft
    # --------------------------------------------------------
    async def finish_draft(self, session: DraftSession):
        session.active = False

        embed = discord.Embed(title="🎉 Résultat de la Draft", color=0xFFD700)

        embed.add_field(
            name=f"Deck de {session.player_a.display_name}",
            value="\n".join(f"- {c}" for c in session.deck_a),
            inline=False
        )

        embed.add_field(
            name=f"Deck de {session.player_b.display_name}",
            value="\n".join(f"- {c}" for c in session.deck_b),
            inline=False
        )

        await session.channel.send(embed=embed)

        self.end_session(session.id)

    # --------------------------------------------------------
    # Nettoyage
    # --------------------------------------------------------
    def end_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]


async def setup(bot):
    await bot.add_cog(Draft(bot))
