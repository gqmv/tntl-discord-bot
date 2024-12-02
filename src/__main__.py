import logging

import discord
import discord.client
from discord.ext import commands

from config import (
    DATABASE_URL,
    DISCORD_TOKEN,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from services.database import DatabaseService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True

bot = discord.bot.Bot(intents=intents)

db_url_defined = DATABASE_URL is not None
db_url_fields_defined = (
    POSTGRES_USER
    and POSTGRES_PASSWORD
    and POSTGRES_DB
    and POSTGRES_HOST
    and POSTGRES_PORT
)

if not db_url_defined and not db_url_fields_defined:
    logger.error("Missing required environment variables")
    raise ValueError("Missing environment variables.")

if db_url_fields_defined and not POSTGRES_PORT.isdigit():  # type: ignore
    logger.error("Invalid POSTGRES_PORT value")
    raise ValueError("POSTGRES_PORT must be a number.")

logger.info("Configuring database connection")
conn_string = (
    DATABASE_URL
    if DATABASE_URL
    else f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

db_service = DatabaseService(conn_string)
db_service.migrate()
logger.info("Database migration completed")


def is_admin(ctx: discord.ApplicationContext):
    user = ctx.author
    channel = ctx.channel

    return channel.permissions_for(user).administrator


@bot.event
async def on_ready():
    logger.info(f"Bot logged in as {bot.user}")
    print(f"Logged in as {bot.user}")


@bot.slash_command(name="ping", description="Ping the bot")
async def ping(ctx):
    logger.debug(f"Ping command received from {ctx.author.id}")
    await ctx.respond("Pong!")


@bot.slash_command(
    name="define-tntl-channel", description="Define the channel for Try Not To Laugh."
)
@commands.check(is_admin)  # type: ignore
async def define_tntl_channel(ctx: discord.ApplicationContext, max_submissions: int):
    channel = ctx.channel

    tntl_channel_id = db_service.get_tntl_channel_id(channel.id)

    if tntl_channel_id:
        logger.warning(f"Attempted to redefine existing TNTL channel {channel.id}")
        await ctx.respond("Try Not To Laugh channel already defined.")
        return

    db_service.define_tntl_channel(channel.id, max_submissions)
    logger.info(f"New TNTL channel defined: {channel.id} with {max_submissions} max submissions")

    await ctx.respond(
        f"Try Not To Laugh channel defined to {channel.mention} with {max_submissions} submissions per message.",
        ephemeral=True,
    )


class TntlMessageView(discord.ui.View):
    def __init__(self, tntl_message_id: int):
        self.tntl_message_id = tntl_message_id
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Upvote", style=discord.ButtonStyle.success, custom_id="upvote_button"
    )
    async def upvote(self, button: discord.ui.Button, interaction: discord.Interaction):
        user = interaction.user

        if not user:
            logger.warning("Upvote attempted without user context")
            await interaction.respond(
                "You must be logged in to upvote.", ephemeral=True
            )
            return

        if not db_service.check_tntl_message_exists(self.tntl_message_id):
            logger.warning(f"Attempted to upvote non-existent message {self.tntl_message_id}")
            await interaction.respond(
                "This message is no longer available.", ephemeral=True
            )
            return

        db_service.upvote_tntl_message(self.tntl_message_id, user.id)
        logger.info(f"Message {self.tntl_message_id} upvoted by user {user.id}")

        await interaction.respond("Upvote submitted.", ephemeral=True)

class NonTntlChannelError(Exception):
    pass

class SubmissionLimitExceededError(Exception):
    pass

async def process_submission(url: str, channel: discord.TextChannel, submitter_id: int):
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

    await channel.send(url, view=TntlMessageView(tntl_message_id))


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
        await process_submission(message_text, message.channel, message_sender_id)  # type: ignore
    except NonTntlChannelError:
        await message.author.send("This is not a Try Not To Laugh channel.")
    except SubmissionLimitExceededError:
        await message.author.send(
            "You have already submitted the maximum number of messages for this channel."
        )

    await message.delete()


@bot.slash_command(
    name="submit-tntl-message", description="Submit a message to Try Not To Laugh."
)
async def submit_tntl_message(ctx: discord.ApplicationContext, url: str):
    try:
        await process_submission(url, ctx.channel, ctx.author.id)
    except NonTntlChannelError:
        await ctx.respond("This is not a Try Not To Laugh channel.", ephemeral=True)
    except SubmissionLimitExceededError:
        await ctx.respond(
            "You have already submitted the maximum number of messages for this channel.",
            ephemeral=True,
        )


@bot.slash_command(name="end-tntl-cycle", description="End the Try Not To Laugh cycle.")
@commands.check(is_admin)  # type: ignore
async def end_tntl_cycle(ctx: discord.ApplicationContext):
    channel_id = ctx.channel.id
    tntl_channel_id = db_service.get_tntl_channel_id(channel_id)

    if not tntl_channel_id:
        logger.warning(f"Attempted to end TNTL cycle in non-TNTL channel {channel_id}")
        await ctx.respond("This is not a Try Not To Laugh channel.", ephemeral=True)
        return

    logger.info(f"Ending TNTL cycle in channel {channel_id}")
    top_upvoted_messages = db_service.get_top_upvoted_messages(tntl_channel_id)

    top_upvoted_messages_text = "Here are the top upvoted messages:\n"

    for message in top_upvoted_messages:
        top_upvoted_messages_text += f"{message.upvote_count} - {message.message_text} - <@{message.sender_id}>\n"

    await ctx.send(top_upvoted_messages_text)

    top_upvoted_user_ids = db_service.get_top_upvoted_user_ids(tntl_channel_id)

    top_upvoted_users_text = "Here are the top upvoted users:\n"

    for user_id in top_upvoted_user_ids:
        top_upvoted_users_text += f"<@{user_id}>\n"

    await ctx.send(top_upvoted_users_text)

    db_service.end_tntl_cycle(tntl_channel_id)
    logger.info(f"TNTL cycle ended in channel {channel_id}")

    await ctx.respond("Try Not To Laugh cycle ended.", ephemeral=True)


if __name__ == "__main__":
    logger.info("Starting bot")
    bot.run(DISCORD_TOKEN)
