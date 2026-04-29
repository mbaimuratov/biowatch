from dataclasses import dataclass
from functools import lru_cache
from os import getenv


@dataclass(frozen=True)
class Settings:
    app_name: str = "BioWatch"
    environment: str = "local"
    database_url: str = "postgresql+asyncpg://biowatch:biowatch@localhost:55432/biowatch"
    redis_url: str = "redis://localhost:56379/0"
    elasticsearch_url: str = "http://localhost:59200"
    elasticsearch_index: str = "biowatch-papers"
    elasticsearch_timeout_seconds: float = 10.0
    europe_pmc_base_url: str = "https://www.ebi.ac.uk/europepmc/webservices/rest"
    europe_pmc_timeout_seconds: float = 10.0
    europe_pmc_max_attempts: int = 3
    europe_pmc_retry_backoff_seconds: float = 0.25
    worker_metrics_port: int = 9100
    scheduler_interval_seconds: int = 60
    telegram_bot_token: str = ""
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-5-mini"
    llm_timeout_seconds: float = 20.0
    summary_prompt_version: str = "v1"
    summary_wait_timeout_seconds: float = 15.0
    pubmed_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=getenv("BIOWATCH_APP_NAME", Settings.app_name),
        environment=getenv("BIOWATCH_ENVIRONMENT", Settings.environment),
        database_url=getenv("BIOWATCH_DATABASE_URL", Settings.database_url),
        redis_url=getenv("BIOWATCH_REDIS_URL", Settings.redis_url),
        elasticsearch_url=getenv(
            "BIOWATCH_ELASTICSEARCH_URL",
            Settings.elasticsearch_url,
        ),
        elasticsearch_index=getenv(
            "BIOWATCH_ELASTICSEARCH_INDEX",
            Settings.elasticsearch_index,
        ),
        elasticsearch_timeout_seconds=float(
            getenv(
                "BIOWATCH_ELASTICSEARCH_TIMEOUT_SECONDS",
                str(Settings.elasticsearch_timeout_seconds),
            )
        ),
        europe_pmc_base_url=getenv(
            "BIOWATCH_EUROPE_PMC_BASE_URL",
            Settings.europe_pmc_base_url,
        ),
        europe_pmc_timeout_seconds=float(
            getenv(
                "BIOWATCH_EUROPE_PMC_TIMEOUT_SECONDS",
                str(Settings.europe_pmc_timeout_seconds),
            )
        ),
        europe_pmc_max_attempts=int(
            getenv(
                "BIOWATCH_EUROPE_PMC_MAX_ATTEMPTS",
                str(Settings.europe_pmc_max_attempts),
            )
        ),
        europe_pmc_retry_backoff_seconds=float(
            getenv(
                "BIOWATCH_EUROPE_PMC_RETRY_BACKOFF_SECONDS",
                str(Settings.europe_pmc_retry_backoff_seconds),
            )
        ),
        worker_metrics_port=int(
            getenv("BIOWATCH_WORKER_METRICS_PORT", str(Settings.worker_metrics_port))
        ),
        scheduler_interval_seconds=int(
            getenv(
                "BIOWATCH_SCHEDULER_INTERVAL_SECONDS",
                str(Settings.scheduler_interval_seconds),
            )
        ),
        telegram_bot_token=getenv("BIOWATCH_TELEGRAM_BOT_TOKEN", Settings.telegram_bot_token),
        llm_provider=getenv("BIOWATCH_LLM_PROVIDER", Settings.llm_provider),
        llm_api_key=getenv("BIOWATCH_LLM_API_KEY", Settings.llm_api_key),
        llm_model=getenv("BIOWATCH_LLM_MODEL", Settings.llm_model),
        llm_timeout_seconds=float(
            getenv("BIOWATCH_LLM_TIMEOUT_SECONDS", str(Settings.llm_timeout_seconds))
        ),
        summary_prompt_version=getenv(
            "BIOWATCH_SUMMARY_PROMPT_VERSION",
            Settings.summary_prompt_version,
        ),
        summary_wait_timeout_seconds=float(
            getenv(
                "BIOWATCH_SUMMARY_WAIT_TIMEOUT_SECONDS",
                str(Settings.summary_wait_timeout_seconds),
            )
        ),
        pubmed_base_url=getenv("BIOWATCH_PUBMED_BASE_URL", Settings.pubmed_base_url),
    )
