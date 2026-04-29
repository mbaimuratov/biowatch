import logging

from telegram import BotCommand
from telegram.ext import Application, CommandHandler

from app.bot import handlers
from app.bot import service as bot_service
from app.core.config import get_settings
from app.observability.logging import configure_logging

logger = logging.getLogger(__name__)


def build_application(token: str) -> Application:
    application = Application.builder().token(token).post_init(set_bot_commands).build()
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("settings", handlers.settings))
    application.add_handler(CommandHandler("topics", handlers.topics))
    application.add_handler(CommandHandler("addtopic", handlers.addtopic))
    application.add_handler(CommandHandler("removetopic", handlers.removetopic))
    application.add_handler(CommandHandler("pause", handlers.pause))
    application.add_handler(CommandHandler("resume", handlers.resume))
    application.add_handler(CommandHandler("count", handlers.count))
    application.add_handler(CommandHandler("time", handlers.time))
    application.add_handler(CommandHandler("timezone", handlers.timezone))
    application.add_handler(CommandHandler("digest", handlers.digest))
    return application


async def set_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(
        [BotCommand(command, description) for command, description in bot_service.BOT_COMMANDS]
    )


def main() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("BIOWATCH_TELEGRAM_BOT_TOKEN is required to start the bot")

    logger.info("Starting BioWatch Telegram bot")
    build_application(settings.telegram_bot_token).run_polling()


if __name__ == "__main__":
    main()
