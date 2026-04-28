import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.metrics import (
    API_REQUEST_ERRORS_TOTAL,
    API_REQUEST_LATENCY_SECONDS,
    API_REQUESTS_TOTAL,
)

logger = logging.getLogger("app.api.requests")


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        started_at = time.perf_counter()
        status_code = 500
        path = request.url.path

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            logger.exception(
                "API request failed",
                extra={
                    "request_method": method,
                    "request_path": path,
                    "status_code": status_code,
                },
            )
            raise
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", path)
            latency = time.perf_counter() - started_at

            API_REQUESTS_TOTAL.labels(
                method=method,
                path=path,
                status=str(status_code),
            ).inc()
            API_REQUEST_LATENCY_SECONDS.labels(method=method, path=path).observe(latency)
            if status_code >= 500:
                API_REQUEST_ERRORS_TOTAL.labels(method=method, path=path).inc()

            logger.info(
                "API request completed",
                extra={
                    "request_method": method,
                    "request_path": path,
                    "status_code": status_code,
                    "duration_seconds": round(latency, 6),
                },
            )


def add_observability(app: FastAPI) -> None:
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
