import discord

from config import logger
from services.database import DatabaseService


def get_tntl_message_view(tntl_submission_id: int, db_service: DatabaseService, bot: discord.Bot):
    class TntlMessageView(discord.ui.View):
        def __init__(
            self, tntl_submission_id: int, db_service: DatabaseService, bot: discord.Bot
        ):
            self.tntl_submission_id = tntl_submission_id
            self.db_service = db_service
            self.bot = bot
            super().__init__(timeout=None)

        @discord.ui.button(
            label="Upvote",
            style=discord.ButtonStyle.success,
            custom_id=f"upvote_button_{tntl_submission_id}",
        )
        async def upvote(self, button: discord.ui.Button, interaction: discord.Interaction):
            user = interaction.user

            if not user:
                await interaction.respond(
                    "You must be logged in to upvote.", ephemeral=True
                )
                return

            if not self.db_service.check_tntl_message_exists(self.tntl_submission_id):
                await interaction.respond(
                    "This message is no longer available. (Error 1)", ephemeral=True
                )
                return

            self.db_service.upvote_tntl_message(self.tntl_submission_id, user.id)

            discord_message_id = (
                self.db_service.get_discord_message_id_by_tntl_submission_id(
                    self.tntl_submission_id
                )
            )
            if not discord_message_id:
                await interaction.respond(
                    "This message is no longer available. (Error 2)", ephemeral=True
                )
                return

            channel = interaction.channel
            if not channel:
                await interaction.respond(
                    "This message is no longer available. (Error 3)", ephemeral=True
                )
                return

            message = await channel.fetch_message(discord_message_id)
            if not message:
                await interaction.respond(
                    "This message is no longer available. (Error 4)", ephemeral=True
                )
                return

            upvote_count = self.db_service.get_upvote_count_by_tntl_submission_id(
                self.tntl_submission_id
            )
            await message.edit(
                embed=get_tntl_message_embed(
                    message.embeds[0].fields[0].value, upvote_count
                )
            )

            logger.info(
                f"User {user.id} upvoted message {self.tntl_submission_id} - {upvote_count} upvotes"
            )

            await interaction.respond("Upvote submitted.", ephemeral=True)

    return TntlMessageView(tntl_submission_id, db_service, bot)


def get_tntl_message_embed(url: str, upvote_count: int):
    return discord.Embed(
        color=discord.Color.blue(),
        fields=[
            discord.EmbedField(name="URL", value=url, inline=False),
            discord.EmbedField(name="Upvotes", value=str(upvote_count), inline=True),
        ],
    )
