from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

TelegramDeliveryStatus = Literal[
    "queued",
    "preparing",
    "ready",
    "send_queued",
    "sending",
    "sent",
    "not_ready",
    "failed",
]


class TelegramDigestDeliveryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_id: int
    paper_id: int
    topic_id: int
    summary_id: int | None = None
    position: int


class TelegramDigestDeliveryMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    delivery_id: int
    position: int
    text: str


class TelegramDigestDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscriber_id: int
    digest_id: int | None
    scheduled_for: datetime
    preparation_started_at: datetime | None
    prepared_at: datetime | None
    send_queued_at: datetime | None
    sent_at: datetime | None
    status: TelegramDeliveryStatus
    error_message: str | None
    items: list[TelegramDigestDeliveryItemRead] = []
    messages: list[TelegramDigestDeliveryMessageRead] = []
