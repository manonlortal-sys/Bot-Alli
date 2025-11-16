# cogs/reactions.py
import discord
from discord.ext import commands

from storage import (
    add_participant,
    remove_participant,
    get_participant_entry,
    incr_leaderboard,
    decr_leaderboard,
    set_outcome,
    set_incomplete,
    get_first_defender,
    is_tracked_message,
    get_message_info,
    get_participants_user_ids,
    delete_message_and_participants,
    get_message_outcome,
    get_message_team,   # 🆕 pour vérifier l’équipe de l’alerte
)

from .alerts import (
    build_ping_embed,
    EMOJI_VICTORY, EMOJI_DEFEAT, EMOJI_INCOMP, EMOJI_JOIN,
    AddDefendersButtonView,
)

from .leaderboard import update_leaderboards

TARGET_EMOJIS = {EMOJI_VICTORY, EMOJI_DEFEAT, EMOJI_INCOMP, EMOJI_JOIN}

# 🆕 Teams ignorées pour les leaderboards
IGNORED_TEAMS = {0, 8}   # 0 = Test, 8 = Prisme


class ReactionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _handle_reaction_event(self, payload: discord.RawReactionActionEvent, is_add: bool):
        if payload.guild_id is None:
            return

        emoji_str = str(payload.emoji)
        if emoji_str not in TARGET_EMOJIS:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        channel = guild.get_channel(payload.channel_id) or guild.get_thread(payload.channel_id)
        if channel is None:
            return

        try:
            msg = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return

        # Seulement les messages suivis
        if not is_tracked_message(msg.id):
            return

        # 🆕 Récupérer la team associée
        team_id = get_message_team(msg.id)

        # 🆕 Déterminer si on doit ignorer le leaderboard
        ignore_lb = team_id in IGNORED_TEAMS

        attach_add_defenders_view = False

        # ----- Gestion du 👍 -----
        if emoji_str == EMOJI_JOIN and payload.user_id != self.bot.user.id:
            current_outcome = get_message_outcome(msg.id)

            if is_add:
                inserted = add_participant(msg.id, payload.user_id, payload.user_id, "reaction")
                if inserted and not ignore_lb:
                    incr_leaderboard(guild.id, "defense", payload.user_id)
                    if current_outcome == "win":
                        incr_leaderboard(guild.id, "win", payload.user_id)
                    elif current_outcome == "loss":
                        incr_leaderboard(guild.id, "loss", payload.user_id)

                first_id = get_first_defender(msg.id)
                if first_id == payload.user_id:
                    attach_add_defenders_view = True

            else:
                entry = get_participant_entry(msg.id, payload.user_id)
                if entry:
                    added_by, source, _ = entry
                    if source == "reaction" and added_by == payload.user_id:
                        removed = remove_participant(msg.id, payload.user_id)
                        if removed and not ignore_lb:
                            decr_leaderboard(guild.id, "defense", payload.user_id)
                            if current_outcome == "win":
                                decr_leaderboard(guild.id, "win", payload.user_id)
                            elif current_outcome == "loss":
                                decr_leaderboard(guild.id, "loss", payload.user_id)

        # ----- Mise à jour état combat -----
        prev_outcome = get_message_outcome(msg.id)

        reactions = {str(r.emoji): r.count for r in msg.reactions}
        win_count  = reactions.get(EMOJI_VICTORY, 0)
        loss_count = reactions.get(EMOJI_DEFEAT,  0)
        inc_count  = reactions.get(EMOJI_INCOMP,  0)

        if win_count > 0 and loss_count == 0:
            new_outcome = "win"
        elif loss_count > 0 and win_count == 0:
            new_outcome = "loss"
        else:
            new_outcome = None

        # Si outcome change → modifier leaderboard (sauf team ignorée)
        if prev_outcome != new_outcome and not ignore_lb:
            participants = get_participants_user_ids(msg.id)

            if prev_outcome == "win":
                for uid in participants:
                    decr_leaderboard(guild.id, "win", uid)
            elif prev_outcome == "loss":
                for uid in participants:
                    decr_leaderboard(guild.id, "loss", uid)

            if new_outcome == "win":
                for uid in participants:
                    incr_leaderboard(guild.id, "win", uid)
            elif new_outcome == "loss":
                for uid in participants:
                    incr_leaderboard(guild.id, "loss", uid)

        # Persist
        set_outcome(msg.id, new_outcome)
        set_incomplete(msg.id, inc_count > 0)

        # ----- MAJ embed -----
        emb = await build_ping_embed(msg)
        first_id_now = get_first_defender(msg.id)

        if attach_add_defenders_view or first_id_now is not None:
            await msg.edit(embed=emb, view=AddDefendersButtonView(self.bot, msg.id))
        else:
            await msg.edit(embed=emb)

        # ----- MAJ leaderboards (si non ignoré) -----
        if not ignore_lb:
            await update_leaderboards(self.bot, guild)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        await self._handle_reaction_event(payload, is_add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        await self._handle_reaction_event(payload, is_add=False)

    # ----- Suppression totale -----
    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.guild_id is None:
            return
        if not is_tracked_message(payload.message_id):
            return

        info = get_message_info(payload.message_id)
        if not info:
            return

        guild_id, creator_id = info
        team_id = get_message_team(payload.message_id)
        ignore_lb = team_id in IGNORED_TEAMS

        participants = get_participants_user_ids(payload.message_id)

        if not ignore_lb:
            for uid in participants:
                decr_leaderboard(guild_id, "defense", uid)
            if creator_id is not None:
                decr_leaderboard(guild_id, "pingeur", creator_id)

            outcome = get_message_outcome(payload.message_id)
            if outcome == "win":
                for uid in participants:
                    decr_leaderboard(guild_id, "win", uid)
            elif outcome == "loss":
                for uid in participants:
                    decr_leaderboard(guild_id, "loss", uid)

        delete_message_and_participants(payload.message_id)

        guild = self.bot.get_guild(guild_id)
        if guild is not None and not ignore_lb:
            await update_leaderboards(self.bot, guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionsCog(bot))
