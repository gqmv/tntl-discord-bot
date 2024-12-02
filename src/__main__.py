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

intents = discord.Intents.default()
intents.message_content = True

bot = discord.bot.Bot(intents=intents)

if not (
    POSTGRES_USER
    and POSTGRES_PASSWORD
    and POSTGRES_DB
    and POSTGRES_HOST
    and POSTGRES_PORT
):
    raise ValueError("Missing environment variables.")

if not POSTGRES_PORT.isdigit():
    raise ValueError("POSTGRES_PORT must be a number.")


conn_string = (
    DATABASE_URL
    if DATABASE_URL
    else f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

db_service = DatabaseService(conn_string)
db_service.migrate()


def is_admin(ctx: discord.ApplicationContext):
    user = ctx.author
    channel = ctx.channel

    return channel.permissions_for(user).administrator


@bot.event
async def on_ready():
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
        raise ValueError("Bot user ID not found.")

    if message_sender_id == bot_user.id:
        return

    await message.delete()
    await message.author.send(
        "Please do not submit messages directly to the channel. Instead, use the `/submit-tntl-message` command."
    )


@bot.slash_command(name="ping", description="Ping the bot")
async def ping(ctx):
    await ctx.respond("Pong!")


@bot.slash_command(
    name="define-tntl-channel", description="Define the channel for Try Not To Laugh."
)
@commands.check(is_admin)  # type: ignore
async def define_tntl_channel(ctx: discord.ApplicationContext, max_submissions: int):
    channel = ctx.channel

    tntl_channel_id = db_service.get_tntl_channel_id(channel.id)

    if tntl_channel_id:
        await ctx.respond("Try Not To Laugh channel already defined.")
        return

    db_service.define_tntl_channel(channel.id, max_submissions)

    await ctx.respond(
        f"Try Not To Laugh channel defined to {channel.mention} with {max_submissions} submissions per message.",
        ephemeral=True,
    )


class TntlMessageView(discord.ui.View):
    def __init__(self, tntl_message_id: int):
        self.tntl_message_id = tntl_message_id
        super().__init__()

    @discord.ui.button(label="Upvote", style=discord.ButtonStyle.success)
    async def upvote(self, button: discord.ui.Button, interaction: discord.Interaction):
        user = interaction.user

        if not user:
            return

        if not db_service.check_tntl_message_exists(self.tntl_message_id):
            await interaction.response.send_message(
                "This message is no longer available.", ephemeral=True
            )
            return

        db_service.upvote_tntl_message(self.tntl_message_id, user.id)

        await interaction.response.send_message("Upvote submitted.", ephemeral=True)


@bot.slash_command(
    name="submit-tntl-message", description="Submit a message to Try Not To Laugh."
)
async def submit_tntl_message(ctx: discord.ApplicationContext, url: str):
    channel_id = ctx.channel.id
    submitter_id = ctx.author.id

    tntl_channel_id = db_service.get_tntl_channel_id(channel_id)

    if not tntl_channel_id:
        await ctx.respond("This is not a Try Not To Laugh channel.", ephemeral=True)
        return

    if not db_service.can_submit_tntl_message(tntl_channel_id, submitter_id):
        await ctx.respond(
            "You have already submitted the maximum number of messages for this channel.",
            ephemeral=True,
        )
        return

    tntl_message_id = db_service.submit_tntl_message(url, tntl_channel_id, submitter_id)

    await ctx.send(url, view=TntlMessageView(tntl_message_id))
    await ctx.respond("Message submitted.", ephemeral=True)


@bot.slash_command(name="end-tntl-cycle", description="End the Try Not To Laugh cycle.")
@commands.check(is_admin)  # type: ignore
async def end_tntl_cycle(ctx: discord.ApplicationContext):
    channel_id = ctx.channel.id
    tntl_channel_id = db_service.get_tntl_channel_id(channel_id)

    if not tntl_channel_id:
        await ctx.respond("This is not a Try Not To Laugh channel.", ephemeral=True)
        return

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

    await ctx.respond("Try Not To Laugh cycle ended.", ephemeral=True)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
