# cogs/verify.py
from __future__ import annotations
from typing import List, Optional, Dict, Tuple, Set

import discord
from discord.ext import commands

from storage import get_teams

# ==== CONFIG ====
DIRECTION_ROLE_ID = 1139555104463257671
VALIDATION_CHANNEL_ID = 1422206524243316837
ARRIVAL_CHANNEL_ID = 1308507542821011567   # Salon d'arrivée
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
    # Lit dynamiquement les teams déclarées + ajoute "Invité"
    opts: List[Tuple[str, int]] = []
    for t in get_teams(guild.id):
        label = str(t["name"])
        role_id = int(t["role_id"])
        opts.append((label, role_id))
    opts.append(("Invité", INVITE_ROLE_ID))
    return opts

def compute_pair_roles(chosen_label: str, chosen_role_id: int, guild: discord.Guild) -> List[int]:
    """
    Règles d'attribution couplée :
      - Wanted <-> Wanted 2
      - HagraTime <-> HagraPaLtime
    """
    name = normalize_name(chosen_label)
    pairs = {("wanted", "wanted 2"), ("hagratime", "hagrapaltime")}
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

def roles_to_names(guild: discord.Guild, role_ids: List[int]) -> List[str]:
    out: List[str] = []
    for rid in role_ids:
        r = guild.get_role(rid)
        if r:
            out.append(r.name)
    return out

def is_direction(member: discord.Member) -> bool:
    return any(r.id == DIRECTION_ROLE_ID for r in member.roles)

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

    async def callback(self, interaction: discord.Interaction):
        # Accuse réception pour éviter "Échec de l'interaction"
        chosen = self.chosen()
        msg = (
            f"🛡️ Guilde sélectionnée : **{chosen[0]}**.\n"
            f"➡️ Clique sur **Envoyer la demande** pour continuer."
        ) if chosen else "Sélection invalide."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

class PseudoModal(discord.ui.Modal, title="📝 Pseudo en jeu"):
    pseudo = discord.ui.TextInput(
        label="Ton pseudo IG",
        placeholder="Ex: Kicard",
        required=True,
        max_length=64,
    )

    def __init__(
        self,
        requester: discord.Member,
        chosen_label: str,
        chosen_role_id: int,
        host_channel_id: Optional[int],
        host_message_id: Optional[int],
    ):
        # Timeout étendu à 1h
        super().__init__(timeout=3600)
        self.requester = requester
        self.chosen_label = chosen_label
        self.chosen_role_id = chosen_role_id
        self.host_channel_id = host_channel_id
        self.host_message_id = host_message_id

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Serveur introuvable.", ephemeral=True)
            return

        validation_channel = guild.get_channel(VALIDATION_CHANNEL_ID)
        if not isinstance(validation_channel, discord.TextChannel):
            await interaction.response.send_message("Canal de validation introuvable.", ephemeral=True)
            return

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

        # Supprimer le message d'accueil une fois la demande envoyée
        if self.host_channel_id and self.host_message_id:
            ch = guild.get_channel(self.host_channel_id)
            if isinstance(ch, discord.TextChannel):
                try:
                    msg = await ch.fetch_message(self.host_message_id)
                    await msg.delete()
                except Exception:
                    pass

        await interaction.response.send_message("✅ Ta demande a bien été envoyée à la Direction. Merci de patienter 🙏", ephemeral=True)

class WelcomeView(discord.ui.View):
    # Timeout étendu à 1h
    def __init__(self, member: discord.Member, options_src: List[Tuple[str, int]]):
        super().__init__(timeout=3600)
        self.member = member
        self.guild_select = GuildSelect(options_src)
        self.add_item(self.guild_select)
        # Pour supprimer le message d'accueil après soumission
        self.host_channel_id: Optional[int] = None
        self.host_message_id: Optional[int] = None

    def set_host_message(self, channel_id: int, message_id: int):
        self.host_channel_id = channel_id
        self.host_message_id = message_id

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
        await interaction.response.send_modal(
            PseudoModal(
                requester=self.member,
                chosen_label=chosen_label,
                chosen_role_id=chosen_role_id,
                host_channel_id=self.host_channel_id,
                host_message_id=self.host_message_id,
            )
        )

# ==== UI: Validation par Direction ====
class ValidationButtons(discord.ui.View):
    # Timeout 24h
    def __init__(self, target_user_id: int, chosen_label: str, chosen_role_id: int):
        super().__init__(timeout=86400)
        self.target_user_id = target_user_id
        self.chosen_label = chosen_label
        self.chosen_role_id = chosen_role_id

    async def _get_target_member(self, guild: discord.Guild) -> Optional[discord.Member]:
        return guild.get_member(self.target_user_id) or await guild.fetch_member(self.target_user_id)

    @discord.ui.button(label="Valider", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member) or not is_direction(interaction.user):
            await interaction.response.send_message("Action réservée à la **Direction**.", ephemeral=True)
            return

        member = await self._get_target_member(interaction.guild)
        if member is None:
            try: await interaction.message.delete()
            except Exception: pass
            await interaction.response.send_message("⚠️ Membre introuvable (a peut-être quitté). Demande supprimée.", ephemeral=True)
            return

        # Rôles base = guilde choisie + pair éventuel + Membre (sauf si Invité)
        base_role_ids: List[int] = [self.chosen_role_id]
        base_role_ids += compute_pair_roles(self.chosen_label, self.chosen_role_id, interaction.guild)
        if normalize_name(self.chosen_label) != "invité" and MEMBER_ROLE_ID not in base_role_ids:
            base_role_ids.append(MEMBER_ROLE_ID)

        applied_names: List[str] = []
        for rid in base_role_ids:
            role = interaction.guild.get_role(rid)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Validation guilde")
                    applied_names.append(role.name)
                except Exception:
                    pass

        # Supprime le message de validation (salon propre)
        try: await interaction.message.delete()
        except Exception: pass

        base_roles_display = ", ".join(applied_names) if applied_names else ", ".join(roles_to_names(interaction.guild, base_role_ids)) or "—"

        await interaction.response.send_message(
            content=(
                f"✅ Validation effectuée pour {member.mention}\n"
                f"🏅 Rôles attribués (base) : **{base_roles_display}**\n"
                f"Que souhaites-tu faire ensuite ?"
            ),
            view=PostValidationChoiceView(
                target_member_id=member.id,
                guild=interaction.guild,
                base_role_ids=base_role_ids,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Refuser", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member) or not is_direction(interaction.user):
            await interaction.response.send_message("Action réservée à la **Direction**.", ephemeral=True)
            return
        try: await interaction.message.delete()
        except Exception: pass
        await interaction.response.send_message("❌ Demande refusée. Message supprimé.", ephemeral=True)

# ==== Étape 2 : Choix après validation (extras / clôturer) ====
class PostValidationChoiceView(discord.ui.View):
    def __init__(self, target_member_id: int, guild: discord.Guild, base_role_ids: List[int]):
        super().__init__(timeout=3600)
        self.target_member_id = target_member_id
        self.guild = guild
        self.base_role_ids = base_role_ids

    @discord.ui.button(label="➕ Ajouter rôles supplémentaires", style=discord.ButtonStyle.primary)
    async def extras(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not is_direction(interaction.user):
            await interaction.response.send_message("Action réservée à la **Direction**.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content="Sélectionne des **rôles supplémentaires** à ajouter (optionnel), puis clique sur **Ajouter** ou **Valider et clôturer**.",
            view=ExtraRolesFlowView(target_member_id=self.target_member_id, guild=self.guild, base_role_ids=self.base_role_ids),
        )

    @discord.ui.button(label="✅ Valider et clôturer", style=discord.ButtonStyle.success)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not is_direction(interaction.user):
            await interaction.response.send_message("Action réservée à la **Direction**.", ephemeral=True)
            return
        base_names = roles_to_names(self.guild, self.base_role_ids)
        await interaction.response.edit_message(
            content=(
                f"🎉 Demande finalisée.\n"
                f"📋 Rôles finaux : **{', '.join(base_names) if base_names else '—'}**"
            ),
            view=None,
        )

# ==== Étapes 3 & 4 : Ajout + Récapitulatif ====
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

class ExtraRolesFlowView(discord.ui.View):
    # Timeout 1h
    def __init__(self, target_member_id: int, guild: discord.Guild, base_role_ids: List[int]):
        super().__init__(timeout=3600)
        self.target_member_id = target_member_id
        self.guild = guild
        self.base_role_ids = base_role_ids
        self.roles_select = ExtraRolesSelect(guild)
        self.add_item(self.roles_select)

    @discord.ui.button(label="➕ Ajouter", style=discord.ButtonStyle.primary, emoji="➕")
    async def add_selected(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not is_direction(interaction.user):
            await interaction.response.send_message("Action réservée à la **Direction**.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        member = self.guild.get_member(self.target_member_id) or await self.guild.fetch_member(self.target_member_id)
        if member is None:
            await interaction.followup.send("⚠️ Membre introuvable.", ephemeral=True)
            return

        chosen_ids = self.roles_select.selected_ids()
        if not chosen_ids:
            await interaction.followup.send("Sélectionne au moins **un rôle** avant d’ajouter, ou **valider et clôturer**.", ephemeral=True)
            return

        applied: List[str] = []
        for rid in chosen_ids:
            role = self.guild.get_role(rid)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Rôles supplémentaires (validation)")
                    applied.append(role.name)
                except Exception:
                    pass

        # Récap automatique après ajout
        extra_names = [r.name for r in member.roles if r.id in EXTRA_ROLE_IDS]
        base_names = roles_to_names(self.guild, self.base_role_ids)
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            content=(
                f"📋 **Récapitulatif — {member.mention}**\n"
                f"🏷️ Rôles de base : **{', '.join(base_names) if base_names else '—'}**\n"
                f"➕ Rôles supplémentaires : **{', '.join(extra_names) if extra_names else '—'}**"
            ),
            view=FinalConfirmView(target_member_id=self.target_member_id, guild=self.guild, base_role_ids=self.base_role_ids),
        )

    @discord.ui.button(label="📋 Récapitulatif", style=discord.ButtonStyle.secondary)
    async def show_recap(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = self.guild.get_member(self.target_member_id) or await self.guild.fetch_member(self.target_member_id)
        if member is None:
            await interaction.response.send_message("⚠️ Membre introuvable.", ephemeral=True)
            return

        base_names = roles_to_names(self.guild, self.base_role_ids)
        extra_names = [r.name for r in member.roles if r.id in EXTRA_ROLE_IDS]

        await interaction.response.edit_message(
            content=(
                f"📋 **Récapitulatif — {member.mention}**\n"
                f"🏷️ Rôles de base : **{', '.join(base_names) if base_names else '—'}**\n"
                f"➕ Rôles supplémentaires : **{', '.join(extra_names) if extra_names else '—'}**"
            ),
            view=FinalConfirmView(target_member_id=self.target_member_id, guild=self.guild, base_role_ids=self.base_role_ids),
        )

# ==== Étape 4bis : Modifier TOUS les rôles (guilde + extras) ====
class ModifyGuildSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, current_base: List[int]):
        options_src = build_guild_options(guild)
        options = [discord.SelectOption(label=label, value=str(role_id)) for (label, role_id) in options_src]
        super().__init__(placeholder="🔽 Choisis la guilde…", min_values=1, max_values=1, options=options)
        self._map = {str(rid): label for (label, rid) in options_src}
        # Pré-sélectionner si possible
        for rid_str, label in self._map.items():
            if int(rid_str) in current_base:
                for opt in self.options:
                    if opt.value == rid_str:
                        opt.default = True
                        break
                break

    def chosen(self) -> Optional[Tuple[str, int]]:
        if not self.values: return None
        rid_str = self.values[0]
        label = self._map.get(rid_str)
        return (label, int(rid_str)) if label is not None else None

class ModifyExtrasSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, current_member: discord.Member):
        options: List[discord.SelectOption] = []
        current_ids: Set[int] = {r.id for r in current_member.roles}
        for rid in EXTRA_ROLE_IDS:
            role = guild.get_role(rid)
            if role:
                options.append(discord.SelectOption(
                    label=role.name, value=str(role.id), default=(role.id in current_ids)
                ))
        super().__init__(
            placeholder="Rôles supplémentaires… (optionnel)",
            min_values=0,
            max_values=len(options) if options else 1,
            options=options or [discord.SelectOption(label="Aucun rôle dispo", value="none", default=True)],
        )

    def selected_ids(self) -> List[int]:
        return [int(v) for v in self.values if v.isdigit()]

class ModifyAllRolesView(discord.ui.View):
    def __init__(self, target_member_id: int, guild: discord.Guild, base_role_ids: List[int]):
        super().__init__(timeout=3600)
        self.target_member_id = target_member_id
        self.guild = guild
        self.base_role_ids = base_role_ids
        member = guild.get_member(target_member_id)

        self.guild_select = ModifyGuildSelect(guild, base_role_ids)
        self.add_item(self.guild_select)

        if member:
            self.extras_selec
