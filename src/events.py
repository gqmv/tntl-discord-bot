import discord

from config import logger
from services.database import DatabaseService
from ui import get_tntl_message_view
from utils import NonTntlChannelError, SubmissionLimitExceededError, process_submission


def register_events(bot: discord.Bot, db_service: DatabaseService):
    @bot.event
    async def on_ready():
        logger.info(f"Bot logged in as {bot.user}")

        submission_ids = db_service.get_tntl_submission_ids()
        for submission_id in submission_ids:
            bot.add_view(get_tntl_message_view(submission_id, db_service, bot))

        print(f"Logged in as {bot.user}")

    @bot.event 
    async def on_message(message: discord.Message):
        discord_channel_id = message.channel.id
        tntl_channel_id = db_service.get_tntl_channel_id(discord_channel_id)

        if not tntl_channel_id:
            return

        message_sender_id = message.author.id
        bot_user = bot.user

        if not bot_user:
            logger.error("Bot user ID not found")
            raise ValueError("Bot user ID not found.")

        if message_sender_id == bot_user.id:
            return

        message_text = message.content
        try:
            await process_submission(
                message_text,
                message.channel,  # type: ignore
                message_sender_id,
                db_service,
            )
            await message.author.send(
                "Your message has been submitted. It will be posted to the channel when the watch party starts.",
            )
        except NonTntlChannelError:
            await message.author.send("This is not a Try Not To Laugh channel.")
        except SubmissionLimitExceededError:
            await message.author.send(
                "You have already submitted the maximum number of messages for this channel."
            )

        await message.delete()
