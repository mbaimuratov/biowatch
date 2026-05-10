from __future__ import annotations

from typing import Any

from app.models import Paper

PAPER_INGESTED_EVENT_TYPE = "paper.ingested"
PAPER_INGESTED_EVENT_VERSION = 1
PAPER_INGESTED_TOPIC = "biowatch.paper.ingested.v1"


def build_paper_ingested_payload(paper: Paper) -> dict[str, Any]:
    return {
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


def paper_ingested_key(paper: Paper) -> str:
    return f"{paper.source}:{paper.source_id}"
