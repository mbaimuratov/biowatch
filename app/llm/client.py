from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings


@dataclass(frozen=True)
class PaperSummaryResult:
    summary_short: str
    key_points: list[str]
    limitations: str
    why_it_matters: str


class PaperSummaryLLMClient(Protocol):
    async def summarize_paper(self, title: str, abstract: str) -> PaperSummaryResult:
        raise NotImplementedError


class PaperSummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_short: str = Field(min_length=1)
    key_points: list[str] = Field(min_length=1, max_length=5)
    limitations: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)


class OpenAIPaperSummaryClient:
    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        if not api_key:
            raise ValueError("BIOWATCH_LLM_API_KEY is required for OpenAI summaries")
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self._model = model

    async def summarize_paper(self, title: str, abstract: str) -> PaperSummaryResult:
        response = await self._client.responses.parse(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You summarize biomedical literature for a morning reading brief. "
                        "Use only the provided title and abstract. Do not invent methods, "
                        "results, limitations, or clinical implications that are not in the "
                        "abstract. Return concise JSON matching the requested schema."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Title:\n{title.strip()}\n\n"
                        f"Abstract:\n{abstract.strip()}\n\n"
                        "Write a one-sentence takeaway, 2-4 key points, limitations, "
                        "and why this paper matters."
                    ),
                },
            ],
            text_format=PaperSummaryOutput,
        )
        parsed = response.output_parsed
        return PaperSummaryResult(
            summary_short=parsed.summary_short.strip(),
            key_points=[point.strip() for point in parsed.key_points if point.strip()],
            limitations=parsed.limitations.strip(),
            why_it_matters=parsed.why_it_matters.strip(),
        )


def build_paper_summary_client(settings: Settings) -> PaperSummaryLLMClient:
    if settings.llm_provider != "openai":
        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
    return OpenAIPaperSummaryClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
