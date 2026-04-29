from collections.abc import Awaitable, Callable

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot import service as bot_service
from app.bot.parsing import BotCommandError
from app.db.session import SessionLocal


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(update, lambda session, identity: bot_service.start(session, identity))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, bot_service.HELP_TEXT)


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(update, lambda session, identity: bot_service.settings(session, identity))


async def topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(update, lambda session, identity: bot_service.list_topics(session, identity))


async def addtopic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(
        update,
        lambda session, identity: bot_service.add_topic(session, identity, _args_text(context)),
    )


async def removetopic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(
        update,
        lambda session, identity: bot_service.remove_topic(session, identity, _args_text(context)),
    )


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(update, lambda session, identity: bot_service.pause(session, identity))


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(update, lambda session, identity: bot_service.resume(session, identity))


async def count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(
        update,
        lambda session, identity: bot_service.set_count(session, identity, _args_text(context)),
    )


async def time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(
        update,
        lambda session, identity: bot_service.set_time(session, identity, _args_text(context)),
    )


async def timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(
        update,
        lambda session, identity: bot_service.set_timezone(session, identity, _args_text(context)),
    )


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run(update, lambda session, identity: bot_service.digest(session, identity))


async def _run(
    update: Update,
    action: Callable[
        [object, bot_service.TelegramIdentity],
        Awaitable[str],
    ],
) -> None:
    try:
        identity = _identity(update)
        async with SessionLocal() as session:
            text = await action(session, identity)
    except BotCommandError as exc:
        text = str(exc)
    await _reply(update, text)


def _identity(update: Update) -> bot_service.TelegramIdentity:
    if update.effective_chat is None:
        raise BotCommandError("This command needs a Telegram chat.")

    user = update.effective_user
    return bot_service.TelegramIdentity(
        chat_id=update.effective_chat.id,
        user_id=user.id if user is not None else None,
        username=user.username if user is not None else None,
        first_name=user.first_name if user is not None else None,
    )


def _args_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    args = getattr(context, "args", None) or []
    return " ".join(args).strip()


async def _reply(update: Update, text: str) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        text,
        disable_web_page_preview=True,
        reply_markup=_suggestion_keyboard(),
    )


def _suggestion_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [list(row) for row in bot_service.SUGGESTED_COMMANDS],
        resize_keyboard=True,
        input_field_placeholder="Choose a BioWatch command or type a topic",
    )
