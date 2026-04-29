from typing import Protocol

from telegram import Bot


class TelegramSender(Protocol):
    async def send_message(self, chat_id: int, text: str) -> None: ...


class TelegramBotSender:
    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("BIOWATCH_TELEGRAM_BOT_TOKEN is required to send Telegram messages")
        self._bot = Bot(token)

    async def send_message(self, chat_id: int, text: str) -> None:
        await self._bot.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=False,
        )
