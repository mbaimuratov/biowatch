from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field


class TelegramSubscriberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_chat_id: int
    telegram_user_id: int | None = None
    username: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default="Europe/Rome", min_length=1, max_length=64)
    morning_send_time: time = time(8, 0)
    article_count: int = Field(default=5, gt=0)
    enabled: bool = True


class TelegramSubscriberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_user_id: int | None = None
    username: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    morning_send_time: time | None = None
    article_count: int | None = Field(default=None, gt=0)
    enabled: bool | None = None


class TelegramSubscriberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_chat_id: int
    telegram_user_id: int | None
    username: str | None
    first_name: str | None
    timezone: str
    morning_send_time: time
    article_count: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
