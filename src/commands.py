import discord
from discord.ext import commands

from checks import is_admin_check
from config import logger
from services.database import DatabaseService
from ui import get_tntl_message_view, get_tntl_message_embed
from utils import NonTntlChannelError, SubmissionLimitExceededError, process_submission


def register_commands(bot: discord.Bot, db_service: DatabaseService):
    @bot.slash_command(name="ping", description="Ping the bot")
    async def ping(ctx):
        logger.debug(f"Ping command received from {ctx.author.id}")
        await ctx.respond("Pong!")

    @bot.slash_command(
        name="define-tntl-channel", description="Define the channel for Try Not To Laugh."
    )
    @commands.check(is_admin_check)  # type: ignore
    async def define_tntl_channel(ctx: discord.ApplicationContext, max_submissions: int):
        channel = ctx.channel

        tntl_channel_id = db_service.get_tntl_channel_id(channel.id)

        if tntl_channel_id:
            logger.warning(f"Attempted to redefine existing TNTL channel {channel.id}")
            await ctx.respond("Try Not To Laugh channel already defined.")
            return

        db_service.define_tntl_channel(channel.id, max_submissions)
        logger.info(
            f"New TNTL channel defined: {channel.id} with {max_submissions} max submissions"
        )

        await ctx.respond(
            f"Try Not To Laugh channel defined to {channel.mention} with {max_submissions} submissions per message.",
            ephemeral=True,
        )

    @bot.slash_command(
        name="submit-tntl-message", description="Submit a message to Try Not To Laugh."
    )
    async def submit_tntl_message(ctx: discord.ApplicationContext, url: str):
        try:
            await process_submission(url, ctx.channel, ctx.author.id, db_service)
            await ctx.respond(
                "Your message has been submitted. It will be posted to the channel when the watch party starts.",
                ephemeral=True,
            )
        except NonTntlChannelError:
            await ctx.respond("This is not a Try Not To Laugh channel.", ephemeral=True)
        except SubmissionLimitExceededError:
            await ctx.respond(
                "You have already submitted the maximum number of messages for this channel.",
                ephemeral=True,
            )

    @bot.slash_command(
        name="start-tntl-watch-party",
        description="Start the Try Not To Laugh watch party.",
    )
    @commands.check(is_admin_check)  # type: ignore
    async def start_tntl_watch_party(ctx: discord.ApplicationContext):
        tntl_channel_id = db_service.get_tntl_channel_id(ctx.channel.id)

        if not tntl_channel_id:
            logger.warning(
                f"Attempted to start TNTL watch party in non-TNTL channel {ctx.channel.id}"
            )
            await ctx.respond("This is not a Try Not To Laugh channel.", ephemeral=True)
            return

        tntl_submissions = db_service.get_tntl_submissions(tntl_channel_id)
        logger.info(
            f"Starting TNTL watch party in channel {tntl_channel_id} with {len(tntl_submissions)} submissions"
        )

        for submission in tntl_submissions:
            submission_message = await ctx.channel.send(
                embed=get_tntl_message_embed(submission.message_text, 0),
                view=get_tntl_message_view(submission.id, db_service, bot),
            )
            db_service.link_tntl_submission_to_discord_message(
                submission.id, submission_message.id
            )

        await ctx.respond("Try Not To Laugh watch party started.", ephemeral=True)

    @bot.slash_command(name="end-tntl-cycle", description="End the Try Not To Laugh cycle.")
    @commands.check(is_admin_check)  # type: ignore
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
