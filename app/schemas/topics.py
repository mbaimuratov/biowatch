from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IngestionFrequency = Literal["daily", "weekly"]


class TopicCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscriber_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    query: str = Field(min_length=1, max_length=1000)
    enabled: bool = True
    ingestion_frequency: IngestionFrequency = "daily"
    priority: int = 0
    max_papers_per_run: int = Field(default=25, gt=0)

    @field_validator("name", "query")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value must not be blank")
        return stripped


class TopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscriber_id: int | None
    name: str
    query: str
    created_at: datetime
    enabled: bool
    ingestion_frequency: IngestionFrequency
    last_ingested_at: datetime | None
    last_successful_ingestion_at: datetime | None
    priority: int
    max_papers_per_run: int
