from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class BotCommandError(ValueError):
    pass


@dataclass(frozen=True)
class TopicCommand:
    name: str
    query: str


def parse_topic_command(text: str) -> TopicCommand:
    name, separator, query = text.partition("|")
    if not separator:
        raise BotCommandError("Use: /addtopic Topic name | search query")

    name = name.strip()
    query = query.strip()
    if not name:
        raise BotCommandError("Topic name must not be blank.")
    if not query:
        raise BotCommandError("Topic query must not be blank.")
    return TopicCommand(name=name, query=query)


def parse_positive_int(text: str, command: str) -> int:
    value = text.strip()
    if not value:
        raise BotCommandError(f"Use: /{command} 5")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise BotCommandError("Value must be a positive integer.") from exc
    if parsed <= 0:
        raise BotCommandError("Value must be a positive integer.")
    return parsed


def parse_time(text: str) -> time:
    value = text.strip()
    if not value:
        raise BotCommandError("Use: /time 08:30")

    parts = value.split(":")
    if len(parts) != 2 or len(parts[0]) != 2 or len(parts[1]) != 2:
        raise BotCommandError("Time must use HH:MM format, for example /time 08:30.")

    try:
        hour = int(parts[0])
        minute = int(parts[1])
        return time(hour, minute)
    except ValueError as exc:
        raise BotCommandError("Time must use HH:MM format, for example /time 08:30.") from exc


def parse_timezone(text: str) -> str:
    timezone = text.strip()
    if not timezone:
        raise BotCommandError("Use: /timezone Europe/Rome")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise BotCommandError("Unknown timezone. Example: /timezone Europe/Rome") from exc
    return timezone
