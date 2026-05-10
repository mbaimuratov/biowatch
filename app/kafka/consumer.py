from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from aiokafka import AIOKafkaConsumer


@dataclass(frozen=True)
class KafkaMessage:
    topic: str
    partition: int
    offset: int
    value: dict[str, Any]


class KafkaConsumer:
    def __init__(
        self,
        topics: list[str],
        bootstrap_servers: str,
        group_id: str,
        client_id: str,
    ) -> None:
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            client_id=client_id,
            enable_auto_commit=False,
            value_deserializer=_decode_json,
        )

    async def start(self) -> None:
        await self._consumer.start()

    async def stop(self) -> None:
        await self._consumer.stop()

    async def commit(self) -> None:
        await self._consumer.commit()

    async def messages(self) -> AsyncIterator[KafkaMessage]:
        async for message in self._consumer:
            yield KafkaMessage(
                topic=message.topic,
                partition=message.partition,
                offset=message.offset,
                value=message.value,
            )


def _decode_json(value: bytes) -> dict[str, Any]:
    decoded = json.loads(value.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Kafka message value must be a JSON object")
    return decoded
