from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import Paper

PAPER_INGESTED_EVENT_TYPE = "paper.ingested"
PAPER_INGESTED_EVENT_VERSION = 1
PAPER_INGESTED_TOPIC = "biowatch.paper.ingested.v1"


class InvalidPaperIngestedEvent(ValueError):
    """Raised when a paper.ingested event cannot be processed."""


@dataclass(frozen=True)
class PaperIngestedEvent:
    event_id: str
    paper_id: int


def build_paper_ingested_payload(paper: Paper) -> dict[str, Any]:
    return {
        "event_id": f"paper.ingested.v1:{paper.id}",
        "event_type": PAPER_INGESTED_EVENT_TYPE,
        "event_version": PAPER_INGESTED_EVENT_VERSION,
        "paper": {
            "id": paper.id,
            "source": paper.source,
            "source_id": paper.source_id,
            "title": paper.title,
            "abstract": paper.abstract,
            "journal": paper.journal,
            "publication_date": paper.publication_date.isoformat()
            if paper.publication_date is not None
            else None,
            "doi": paper.doi,
            "url": paper.url,
            "created_at": paper.created_at.isoformat(),
        },
    }


def parse_paper_ingested_event(payload: dict[str, Any]) -> PaperIngestedEvent:
    if payload.get("event_type") != PAPER_INGESTED_EVENT_TYPE:
        raise InvalidPaperIngestedEvent("invalid event_type")
    if payload.get("event_version") != PAPER_INGESTED_EVENT_VERSION:
        raise InvalidPaperIngestedEvent("invalid event_version")

    paper = payload.get("paper")
    if not isinstance(paper, dict):
        raise InvalidPaperIngestedEvent("missing paper object")

    paper_id = paper.get("id")
    if not isinstance(paper_id, int) or paper_id <= 0:
        raise InvalidPaperIngestedEvent("missing valid paper.id")

    event_id = payload.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        event_id = f"paper.ingested.v1:{paper_id}"

    return PaperIngestedEvent(event_id=event_id, paper_id=paper_id)


def paper_ingested_key(paper: Paper) -> str:
    return f"{paper.source}:{paper.source_id}"
