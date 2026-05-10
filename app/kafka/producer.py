from __future__ import annotations

import json
from typing import Any

from aiokafka import AIOKafkaProducer


class KafkaProducer:
    def __init__(self, bootstrap_servers: str, client_id: str) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            key_serializer=lambda value: value.encode("utf-8") if value is not None else None,
        )

    async def start(self) -> None:
        await self._producer.start()

    async def publish(self, topic: str, payload: dict[str, Any], key: str | None = None) -> None:
        await self._producer.send_and_wait(topic, value=payload, key=key)

    async def stop(self) -> None:
        await self._producer.stop()
