# cogs/verify.py
from __future__ import annotations
from typing import List, Optional, Dict, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from storage import get_teams

# ==== CONFIG (adapter si besoin) ====
DIRECTION_ROLE_ID = 1139555104463257671
VALIDATION_CHANNEL_ID = 1422206524243316837
INVITE_ROLE_ID = 1139574688255844484
MEMBER_ROLE_ID = 1139556803638726717

# Rôles supplémentaires proposés après validation (whitelist)
EXTRA_ROLE_IDS: List[int] = [
    DIRECTION_ROLE_ID,        # Direction
    1421953218719518961,      # Prisme
]


# ==== Utilitaires ====
def normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def build_guild_options(guild: discord.Guild) -> List[Tuple[str, int]]:
    """
    Retourne une liste [(label lisible, role_id)] à proposer au nouveau membre.
    On lit dynamiquement les teams depuis la DB + ajoute 'Invité'.
    """
    opts: List[Tuple[str, int]] = []
    for t in get_teams(guild.id):
        label = str(t["name"])
        role_id = int(t["role_id"])
        opts.append((label, role_id))
    # Ajoute "Invité"
    opts.append(("Invité", INVITE_ROLE_ID))
    return opts


def compute_pair_roles(chosen_label: str, chosen_role_id: int, guild: discord.Guild) -> List[int]:
    """
    Règles d'attribution couplée :
      - Wanted <-> Wanted 2
      - HagraTime <-> HagraPaLtime
    Retourne une liste d'IDs rôles à ajouter en plus du choisi, si applicable.
    """
    name = normalize_name(chosen_label)
    pairs = {
        ("wanted", "wanted 2"),
        ("hagratime", "hagrapaltime"),
    }

    # Fabrique un mapping name->role_id pour lookup rapide
    name_to_role_id: Dict[str, int] = {}
    for (label, role_id) in build_guild_options(guild):
        name_to_role_id[normalize_name(label)] = role_id

    extra: List[int] = []
    for a, b in pairs:
        if name == a and b in name_to_role_id:
            extra.append(name_to_role_id[b])
        elif name == b and a in name_to_role_id:
            extra.append(name_to_role_id[a])
    return extra


# ==== UI: Sélecteur de guilde + bouton d'envoi ====
class GuildSelect(discord.ui.Select):
    def __init__(self, options_src: List[Tuple[str, int]]):
        options = [
            discord.SelectOption(label=label, value=str(role_id))
            for (label, role_id) in options_src
        ]
        super().__init__(
            placeholder="🔽 Sélectionne ta guilde…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self._options_src = {str(role_id): label for (label, role_id) in options_src}

    def chosen(self) -> Optional[Tuple[str, int]]:
        if not self.values:
            return None
        role_id_str = self.values[0]
        label = self._options_src.get(role_id_str)
        if label is None:
            return None
        return (label, int(role_id_str))


class PseudoModal(discord.ui.Modal, title="📝 Pseudo en jeu"):
    pseudo = discord.ui.TextInput(
        label="Ton pseudo IG",
        placeholder="Ex: Kicard",
        required=True,
        max_length=64,
    )

    def __init__(self, requester: discord.Member, chosen_label: str, chosen_role_id: int):
        super().__init__(timeout=300)
        self.requester = requester
        self.chosen_label = chosen_label
        self.chosen_role_id = chosen_role_id

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Serveur introuvable.", ephemeral=True)
            return

        validation_channel = guild.get_channel(VALIDATION_CHANNEL_ID)
        if not isinstance(validation_channel, discord.TextChannel):
            await interaction.response.send_message("Canal de validation introuvable.", ephemeral=True)
            return

        # Embed de demande pour Direction
        embed = discord.Embed(
            title="📝 Nouvelle demande de validation",
            description=(
                f"👤 Joueur : **{self.requester.mention}**\n"
                f"🎮 Pseudo IG : **{str(self.pseudo)}**\n"
                f"🏷️ Guilde demandée : **{self.chosen_label}**\n\n"
                f"📌 **Rappels auto :**\n"
                f"🔹 Validation = ajoute aussi le rôle **Membre**.\n"
                f"🔹 Wanted ↔ Wanted 2 : les **deux rôles** sont attribués.\n"
                f"🔹 HagraTime ↔ HagraPaLtime : les **deux rôles** sont attribués.\n"
                f"🔹 Invité = attribue seulement le rôle *Invité*."
            ),
            color=discord.Color.blurple(),
        )

        view = ValidationButtons(
            target_user_id=self.requester.id,
            chosen_label=self.chosen_label,
            chosen_role_id=self.chosen_role_id,
        )

        await validation_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Ta demande a bien été envoyée à la Direction. Merci de patienter 🙏", ephemeral=True)


class WelcomeView(discord.ui.View):
    def __init__(self, member: discord.Member, options_src: List[Tuple[str, int]]):
        super().__init__(timeout=600)
        self.member = member
        self.guild_select = GuildSelect(options_src)
        self.add_item(self.guild_select)

    @discord.ui.button(label="Envoyer la demande", style=discord.ButtonStyle.primary, emoji="📨")
    async def send_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.member.id:
            await interaction.response.send_message("Seul le joueur accueilli peut envoyer sa demande.", ephemeral=True)
            return

        chosen = self.guild_select.chosen()
        if not chosen:
            await interaction.response.send_message("Sélectionne d’abord ta **guilde**.", ephemeral=True)
            return

        chosen_label, chosen_role_id = chosen
        await interaction.response.send_modal(PseudoModal(self.member, chosen_label, chosen_role_id))


# ==== UI: Validation par Direction ====
class ValidationButtons(discord.ui.View):
    def __init__(self, target_user_id: int, chosen_label: str, chosen_role_id: int):
        super().__init__(timeout=86400)
        self.target_user_id = target_user_id
        self.chosen_label = chosen_label
        self.chosen_role_id = chosen_role_id

    def _is_direction(self, user: discord.Member) -> bool:
        return any(r.id == DIRECTION_ROLE_ID for r in user.roles)

    async def _get_target_member(self, guild: discord.Guild) -> Optional[discord.Member]:
        return guild.get_member(self.target_user_id) or await guild.fetch_member(self.target_user_id)

    @discord.ui.button(label="Valider", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        if not isinstance(interaction.user, discord.Member) or not self._is_direction(interaction.user):
            await interaction.response.send_message("Action réservée à la **Direction**.", ephemeral=True)
            return

        member = await self._get_target_member(interaction.guild)
        if member is None:
            # Supprime le message (archivage silencieux) puis notifie
            try:
                await interaction.message.delete()
            except Exception:
                pass
            await interaction.response.send_message("⚠️ Membre introuvable (a peut-être quitté). Demande supprimée.", ephemeral=True)
            return

        # Rôles à attribuer : guilde choisie + pairs + membre
        roles_to_add: List[int] = [self.chosen_role_id]
        roles_to_add += compute_pair_roles(self.chosen_label, self.chosen_role_id, interaction.guild)
        if MEMBER_ROLE_ID not in roles_to_add:
            roles_to_add.append(MEMBER_ROLE_ID)

        # Appliquer
        applied: List[str] = []
        for rid in roles_to_add:
            role = interaction.guild.get_role(rid)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Validation guilde")
                    applied.append(role.name)
                except Exception:
                    pass

        # Supprime le message de validation immédiatement (comme demandé)
        try:
            await interaction.message.delete()
        except Exception:
            pass

        # Proposer des rôles supplémentaires (éphemère pour le validateur)
        await interaction.response.send_message(
            content=(
                f"✅ Validation effectuée pour {member.mention}\n"
                f"🏅 Rôles attribués : **{', '.join(applied) if applied else '—'}**\n"
                f"➕ Tu peux ajouter des **rôles supplémentaires** ci-dessous (facultatif)."
            ),
            view=ExtraRolesView(target_member_id=member.id),
            ephemeral=True,
        )

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return
        if not isinstance(interaction.user, discord.Member) or not self._is_direction(interaction.user):
            await interaction.response.send_message("Action réservée à la **Direction**.", ephemeral=True)
            return

        # Supprime le message et confirme
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await interaction.response.send_message("❌ Demande refusée. Message supprimé.", ephemeral=True)


# ==== UI: Ajout de rôles supplémentaires (après validation) ====
class ExtraRolesSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options: List[discord.SelectOption] = []
        for rid in EXTRA_ROLE_IDS:
            role = guild.get_role(rid)
            if role:
                options.append(discord.SelectOption(label=role.name, value=str(role.id)))
        super().__init__(
            placeholder="Sélectionne des rôles supplémentaires… (optionnel)",
            min_values=0,
            max_values=len(options) if options else 1,
            options=options or [discord.SelectOption(label="Aucun rôle dispo", value="none", default=True)],
        )

    def selected_ids(self) -> List[int]:
        return [int(v) for v in self.values if v.isdigit()]


class ExtraRolesView(discord.ui.View):
    def __init__(self, target_member_id: int):
        super().__init__(timeout=300)
        self.target_member_id = target_member_id
        self.roles_select: Optional[ExtraRolesSelect] = None

    async def on_timeout(self):
        # rien de spécial à faire (vue ephémère)
        pass

    @discord.ui.button(label="Actualiser la liste", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            return
        # Remplace/ajoute le select dynamiquement
        if self.roles_select:
            self.remove_item(self.roles_select)
        self.roles_select = ExtraRolesSelect(guild)
        self.add_item(self.roles_select)
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Ajouter les rôles sélectionnés", style=discord.ButtonStyle.primary, emoji="➕")
    async def add_selected(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            return
        if not isinstance(interaction.user, discord.Member) or not any(r.id == DIRECTION_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("Action réservée à la **Direction**.", ephemeral=True)
            return

        member = guild.get_member(self.target_member_id) or await guild.fetch_member(self.target_member_id)
        if member is None:
            await interaction.response.send_message("⚠️ Membre introuvable.", ephemeral=True)
            return

        if self.roles_select is None:
            self.roles_select = ExtraRolesSelect(guild)

        chosen_ids = self.roles_select.selected_ids()
        applied: List[str] = []
        for rid in chosen_ids:
            role = guild.get_role(rid)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Rôles supplémentaires (validation)")
                    applied.append(role.name)
                except Exception:
                    pass

        await interaction.response.edit_message(
            content=(
                f"✅ Rôles ajoutés : **{', '.join(applied) if applied else '—'}**\n"
                f"🎉 La demande est terminée."
            ),
            view=None,
        )


# ==== COG ====
class VerifyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Message d'accueil auto (pas de DM) — on utilise le salon système s'il existe.
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        channel: Optional[discord.TextChannel] = guild.system_channel  # salon d'arrivée typique
        if channel is None:
            # Si aucun salon système, on essaie de trouver un texte où le bot peut écrire
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        if channel is None:
            return

        options = build_guild_options(guild)
        view = WelcomeView(member, options)
        try:
            await channel.send(
                content=(
                    f"👋 Bienvenue {member.mention} !\n"
                    f"🛡️ Merci de sélectionner ta **guilde** ci-dessous et d’indiquer ton **pseudo en jeu**.\n"
                    f"✨ Ta demande sera transmise à la **Direction** pour validation."
                ),
                view=view,
            )
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(VerifyCog(bot))
