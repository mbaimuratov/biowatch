from fastapi.testclient import TestClient


def test_create_get_and_list_topics(client: TestClient) -> None:
    create_response = client.post(
        "/topics",
        json={
            "name": "Checkpoint inhibitors",
            "query": "cancer immunotherapy checkpoint inhibitor",
        },
    )

    assert create_response.status_code == 201
    created_topic = create_response.json()
    assert created_topic["id"] == 1
    assert created_topic["name"] == "Checkpoint inhibitors"
    assert created_topic["query"] == "cancer immunotherapy checkpoint inhibitor"
    assert created_topic["enabled"] is True
    assert created_topic["created_at"]

    get_response = client.get("/topics/1")

    assert get_response.status_code == 200
    assert get_response.json() == created_topic

    list_response = client.get("/topics")

    assert list_response.status_code == 200
    assert list_response.json() == [created_topic]


def test_create_topic_rejects_blank_text(client: TestClient) -> None:
    response = client.post(
        "/topics",
        json={
            "name": " ",
            "query": " ",
        },
    )

    assert response.status_code == 422
