from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PaperRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_id: str
    title: str
    abstract: str | None
    journal: str | None
    publication_date: date | None
    doi: str | None
    url: str | None
    created_at: datetime
