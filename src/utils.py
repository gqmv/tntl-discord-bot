import discord

from config import logger
from services.database import DatabaseService


class NonTntlChannelError(Exception):
    pass


class SubmissionLimitExceededError(Exception):
    pass


async def process_submission(
    url: str,
    channel: discord.TextChannel,
    submitter_id: int,
    db_service: DatabaseService,
):
    tntl_channel_id = db_service.get_tntl_channel_id(channel.id)

    if not tntl_channel_id:
        logger.warning(f"Attempted to submit message to non-TNTL channel {channel.id}")
        raise NonTntlChannelError

    if not db_service.can_submit_tntl_message(tntl_channel_id, submitter_id):
        logger.info(
            f"User {submitter_id} exceeded submission limit in channel {channel.id}"
        )
        raise SubmissionLimitExceededError

    tntl_message_id = db_service.submit_tntl_message(url, tntl_channel_id, submitter_id)
    logger.info(f"New TNTL message {tntl_message_id} submitted by user {submitter_id}")
