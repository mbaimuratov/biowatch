import asyncio
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from sqlalchemy import func, select

from app.models import Digest, DigestItem, Paper, Topic, TopicPaper
from app.services import digests as digest_service

NOW = datetime(2026, 4, 29, 8, 0, tzinfo=UTC)


def test_digest_tables_can_persist_digest_items(async_session_factory) -> None:
    async def scenario() -> dict[str, object]:
        async with async_session_factory() as session:
            topic = Topic(name="Checkpoint inhibitors", query="checkpoint")
            paper = Paper(source="europe_pmc", source_id="MED:1", title="Checkpoint paper")
            session.add_all([topic, paper])
            await session.flush()
            digest = Digest(digest_date=date(2026, 4, 29), generated_at=NOW, paper_count=1)
            session.add(digest)
            await session.flush()
            session.add(
                DigestItem(
                    digest_id=digest.id,
                    paper_id=paper.id,
                    topic_id=topic.id,
                    rank=1,
                    reason="Matched topic: Checkpoint inhibitors",
                )
            )
            await session.commit()

            persisted_digest = await session.scalar(select(Digest))
            persisted_item = await session.scalar(select(DigestItem))
            return {
                "digest_date": persisted_digest.digest_date,
                "paper_count": persisted_digest.paper_count,
                "rank": persisted_item.rank,
                "is_new": persisted_item.is_new,
                "is_saved": persisted_item.is_saved,
                "is_dismissed": persisted_item.is_dismissed,
            }

    assert asyncio.run(scenario()) == {
        "digest_date": date(2026, 4, 29),
        "paper_count": 1,
        "rank": 1,
        "is_new": True,
        "is_saved": False,
        "is_dismissed": False,
    }


def test_generate_today_digest_creates_ranked_items_and_is_idempotent(
    async_session_factory,
) -> None:
    asyncio.run(_create_digest_source_data(async_session_factory))

    first = asyncio.run(_generate_and_load(async_session_factory))
    second = asyncio.run(_generate_and_load(async_session_factory))

    assert first["digest_count"] == 1
    assert first["item_count"] == 2
    assert first["paper_count"] == 2
    assert first["items"] == [
        (1, "Newer publication", "Matched topic: Checkpoint inhibitors"),
        (2, "Older publication", "Matched topic: Checkpoint inhibitors"),
    ]
    assert second["digest_count"] == 1
    assert second["item_count"] == 2
    assert second["items"] == first["items"]

    metrics_text = generate_latest().decode()
    assert 'biowatch_digest_generations_total{status="generated"}' in metrics_text
    assert "biowatch_digest_items_generated_total" in metrics_text
    assert "biowatch_digest_generation_duration_seconds_bucket" in metrics_text


def test_get_today_digest_returns_404_before_generation(client: TestClient) -> None:
    response = client.get("/digests/today")

    assert response.status_code == 404
    assert response.json()["detail"] == "Digest not found"


def test_digest_api_generates_and_returns_today_digest(
    client: TestClient,
    async_session_factory,
) -> None:
    asyncio.run(_create_digest_source_data(async_session_factory))

    generate_response = client.post("/digests/today/generate")

    assert generate_response.status_code == 201
    generated = generate_response.json()
    assert generated["digest_date"]
    assert generated["status"] == "generated"
    assert generated["summary_status"] == "not_started"
    assert generated["paper_count"] == 2
    assert [item["rank"] for item in generated["items"]] == [1, 2]
    assert generated["items"][0]["paper"]["title"] == "Newer publication"
    assert generated["items"][0]["topic_name"] == "Checkpoint inhibitors"

    today_response = client.get("/digests/today")

    assert today_response.status_code == 200
    today = today_response.json()
    assert today["id"] == generated["id"]
    assert today["digest_date"] == generated["digest_date"]
    assert today["paper_count"] == generated["paper_count"]
    assert [item["paper"]["title"] for item in today["items"]] == [
        item["paper"]["title"] for item in generated["items"]
    ]

    by_date_response = client.get(f"/digests/{generated['digest_date']}")

    assert by_date_response.status_code == 200
    assert by_date_response.json()["id"] == generated["id"]

    missing_response = client.get("/digests/1999-01-01")

    assert missing_response.status_code == 404


def test_digest_dashboard_renders_empty_and_generated_states(
    client: TestClient,
    async_session_factory,
) -> None:
    empty_response = client.get("/digest/today")

    assert empty_response.status_code == 200
    assert "No digest has been generated for today yet." in empty_response.text
    assert "Generate Today" in empty_response.text

    asyncio.run(_create_digest_source_data(async_session_factory))

    generate_response = client.post("/digest/today/generate", follow_redirects=False)

    assert generate_response.status_code == 303
    assert generate_response.headers["location"] == "/digest/today?message=Digest%20generated"

    generated_response = client.get(generate_response.headers["location"])

    assert generated_response.status_code == 200
    assert "Digest generated" in generated_response.text
    assert "Newer publication" in generated_response.text
    assert "Checkpoint Journal" in generated_response.text
    assert "2025-01-01" in generated_response.text
    assert "Checkpoint inhibitors" in generated_response.text
    assert "Matched topic: Checkpoint inhibitors" in generated_response.text
    assert "https://example.test/newer" in generated_response.text


async def _create_digest_source_data(async_session_factory) -> None:
    async with async_session_factory() as session:
        enabled_topic = Topic(name="Checkpoint inhibitors", query="checkpoint", enabled=True)
        disabled_topic = Topic(name="Disabled topic", query="disabled", enabled=False)
        session.add_all([enabled_topic, disabled_topic])
        await session.flush()

        newer = Paper(
            source="europe_pmc",
            source_id="MED:newer",
            title="Newer publication",
            journal="Checkpoint Journal",
            publication_date=date(2025, 1, 1),
            url="https://example.test/newer",
            created_at=NOW - timedelta(hours=1),
        )
        older = Paper(
            source="europe_pmc",
            source_id="MED:older",
            title="Older publication",
            journal="Older Journal",
            publication_date=date(2024, 1, 1),
            created_at=NOW - timedelta(hours=2),
        )
        disabled = Paper(
            source="europe_pmc",
            source_id="MED:disabled",
            title="Disabled topic publication",
            publication_date=date(2026, 1, 1),
            created_at=NOW,
        )
        stale = Paper(
            source="europe_pmc",
            source_id="MED:stale",
            title="Stale publication",
            publication_date=date(2026, 1, 2),
            created_at=NOW,
        )
        session.add_all([newer, older, disabled, stale])
        await session.flush()

        session.add_all(
            [
                TopicPaper(
                    topic_id=enabled_topic.id,
                    paper_id=older.id,
                    matched_at=NOW - timedelta(hours=3),
                ),
                TopicPaper(
                    topic_id=enabled_topic.id,
                    paper_id=newer.id,
                    matched_at=NOW - timedelta(hours=2),
                ),
                TopicPaper(
                    topic_id=disabled_topic.id,
                    paper_id=disabled.id,
                    matched_at=NOW - timedelta(hours=1),
                ),
                TopicPaper(
                    topic_id=enabled_topic.id,
                    paper_id=stale.id,
                    matched_at=NOW - timedelta(hours=25),
                ),
            ]
        )
        await session.commit()


async def _generate_and_load(async_session_factory) -> dict[str, object]:
    async with async_session_factory() as session:
        digest = await digest_service.generate_today_digest(session, now=NOW)
        digest_count = await session.scalar(select(func.count(Digest.id)))
        item_count = await session.scalar(select(func.count(DigestItem.id)))
        return {
            "digest_count": digest_count,
            "item_count": item_count,
            "paper_count": digest.paper_count,
            "items": [
                (item.rank, item.paper.title, item.reason)
                for item in sorted(digest.items, key=lambda digest_item: digest_item.rank)
            ],
        }
