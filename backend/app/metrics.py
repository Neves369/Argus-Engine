from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "argus_http_requests_total",
    "Total de requisições HTTP processadas.",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "argus_http_request_duration_seconds",
    "Duração das requisições HTTP.",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

BUILD_INFO = Gauge(
    "argus_build_info",
    "Informação de build/versão (valor fixo 1).",
    ["app"],
)

# Path das próprias métricas é excluído para evitar ruído.
METRICS_PATH = "/metrics"


def record_request(method: str, path: str, status: int, duration: float) -> None:
    HTTP_REQUESTS.labels(method, path, status).inc()
    HTTP_REQUEST_DURATION.labels(method, path).observe(duration)


async def metrics_response() -> bytes:
    """Renderiza as métricas no formato de texto do Prometheus."""
    return generate_latest()


def metrics_headers() -> dict[str, str]:
    return {"content-type": CONTENT_TYPE_LATEST}


class MetricsMiddleware:
    """Middlewares ASGI puro que observa requisições HTTP do app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        method = scope.get("method", "")
        if path == METRICS_PATH:
            return await self.app(scope, receive, send)

        status = {"value": 0}
        start = time.perf_counter()

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                status["value"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            record_request(method, path, status["value"] or 500, time.perf_counter() - start)