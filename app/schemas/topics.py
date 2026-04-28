from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    query: str = Field(min_length=1, max_length=1000)
    enabled: bool = True

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
