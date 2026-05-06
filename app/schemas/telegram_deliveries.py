from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

TelegramDeliveryStatus = Literal["queued", "sending", "sent", "failed"]


class TelegramDigestDeliveryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_id: int
    paper_id: int
    topic_id: int
    position: int


class TelegramDigestDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscriber_id: int
    digest_id: int | None
    scheduled_for: datetime
    sent_at: datetime | None
    status: TelegramDeliveryStatus
    error_message: str | None
    items: list[TelegramDigestDeliveryItemRead] = []
