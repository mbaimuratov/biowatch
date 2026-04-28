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
