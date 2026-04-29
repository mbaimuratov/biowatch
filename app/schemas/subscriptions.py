from pydantic import BaseModel


class SubscriptionIngestDueRead(BaseModel):
    topics_checked: int
    topics_enqueued: int
    ingestion_run_ids: list[int]
    job_ids: list[str]
