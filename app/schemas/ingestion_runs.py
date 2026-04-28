from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    status: str
    job_id: str | None
    started_at: datetime
    finished_at: datetime | None
    records_fetched: int
    error_message: str | None
