from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.papers import PaperRead


class DigestItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    digest_id: int
    paper_id: int
    topic_id: int
    topic_name: str
    rank: int
    reason: str | None
    is_new: bool
    is_saved: bool
    is_dismissed: bool
    created_at: datetime
    paper: PaperRead


class DigestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    digest_date: date
    status: str
    created_at: datetime
    generated_at: datetime | None
    paper_count: int
    summary_status: str
    items: list[DigestItemRead]
