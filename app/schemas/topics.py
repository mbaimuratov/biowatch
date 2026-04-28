from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IngestionFrequency = Literal["daily", "weekly"]


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    query: str = Field(min_length=1, max_length=1000)
    enabled: bool = True
    ingestion_frequency: IngestionFrequency = "daily"
    max_results_per_run: int = Field(default=25, gt=0)

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
    name: str
    query: str
    created_at: datetime
    enabled: bool
    ingestion_frequency: IngestionFrequency
    last_ingested_at: datetime | None
    last_successful_ingestion_at: datetime | None
    max_results_per_run: int
