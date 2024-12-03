import discord

from commands import register_commands
from config import (
    DATABASE_URL,
    DISCORD_TOKEN,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    logger,
)
from events import register_events
from services.database import DatabaseService

# Configs

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

# Database service setup

db_service = DatabaseService(conn_string)
db_service.migrate()
logger.info("Database migration completed")

# Register commands
register_commands(bot, db_service)

# Register events
register_events(bot, db_service)


if __name__ == "__main__":
    logger.info("Starting bot")
    bot.run(DISCORD_TOKEN)
