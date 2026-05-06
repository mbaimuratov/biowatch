from prometheus_client import Counter, Gauge, Histogram

API_REQUESTS_TOTAL = Counter(
    "biowatch_api_requests_total",
    "Total API requests.",
    ("method", "path", "status"),
)

API_REQUEST_ERRORS_TOTAL = Counter(
    "biowatch_api_request_errors_total",
    "Total API requests with 5xx responses or unhandled exceptions.",
    ("method", "path"),
)

API_REQUEST_LATENCY_SECONDS = Histogram(
    "biowatch_api_request_latency_seconds",
    "API request latency in seconds.",
    ("method", "path"),
)

INGESTION_JOBS_TOTAL = Counter(
    "biowatch_ingestion_jobs_total",
    "Total ingestion jobs by status.",
    ("status",),
)

INGESTION_JOB_DURATION_SECONDS = Histogram(
    "biowatch_ingestion_job_duration_seconds",
    "Ingestion job duration in seconds.",
    ("status",),
)

INGESTION_RECORDS_FETCHED_TOTAL = Counter(
    "biowatch_ingestion_records_fetched_total",
    "Total Europe PMC records fetched by completed ingestion jobs.",
)

INGESTION_JOBS_IN_PROGRESS = Gauge(
    "biowatch_ingestion_jobs_in_progress",
    "Current ingestion jobs being processed by this worker.",
)

DIGEST_GENERATIONS_TOTAL = Counter(
    "biowatch_digest_generations_total",
    "Total digest generation attempts by status.",
    ("status",),
)

DIGEST_ITEMS_GENERATED_TOTAL = Counter(
    "biowatch_digest_items_generated_total",
    "Total digest items generated.",
)

DIGEST_GENERATION_DURATION_SECONDS = Histogram(
    "biowatch_digest_generation_duration_seconds",
    "Digest generation duration in seconds.",
    ("status",),
)

TELEGRAM_DELIVERY_ATTEMPTS_TOTAL = Counter(
    "biowatch_telegram_delivery_attempts_total",
    "Total Telegram digest delivery attempts by status.",
    ("status",),
)

TELEGRAM_DELIVERY_DURATION_SECONDS = Histogram(
    "biowatch_telegram_delivery_duration_seconds",
    "Telegram digest delivery duration in seconds.",
    ("status",),
)

TELEGRAM_DELIVERY_ITEMS_SENT_TOTAL = Counter(
    "biowatch_telegram_delivery_items_sent_total",
    "Total Telegram digest delivery items sent.",
)

TELEGRAM_DELIVERIES_IN_PROGRESS = Gauge(
    "biowatch_telegram_deliveries_in_progress",
    "Current Telegram digest deliveries being processed by this worker.",
)
