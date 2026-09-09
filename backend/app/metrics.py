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

RUNS_TOTAL = Counter(
    "argus_runs_total",
    "Runs finalizados por status (completed/failed/cancelled/pending_review).",
    ["status"],
)

RUNS_ACTIVE = Gauge(
    "argus_runs_active",
    "Indica se há um run ativo (running ou pending_review) — lock de run único.",
)

RUN_STARTED_AT = Gauge(
    "argus_run_started_at_seconds",
    "Época (Unix) em que o run ativo começou; 0 se não há run ativo.",
)

KILL_SWITCH_ACTIVE = Gauge(
    "argus_kill_switch_active",
    "1 enquanto o kill-switch estiver ativo; 0 caso contrário.",
)

# Path das próprias métricas é excluído para evitar ruído.
METRICS_PATH = "/metrics"


def record_request(method: str, path: str, status: int, duration: float) -> None:
    HTTP_REQUESTS.labels(method, path, status).inc()
    HTTP_REQUEST_DURATION.labels(method, path).observe(duration)


def record_run_start(started_at: float | None = None) -> None:
    """Marca o início de um run: ativa o gauge e grava o instante de início."""
    RUNS_ACTIVE.set(1)
    RUN_STARTED_AT.set(started_at if started_at is not None else time.time())


def record_run_terminal(status: str) -> None:
    """Registra a passagem de um run por um estado terminal.

    `completed`, `failed` e `cancelled` desativam o run. `pending_review`
    também conta como finalização (estatística), mas mantém o run ativo: a
    retomada/revisão continua sob o mesmo lock de run único.
    """
    if status == "running":
        return
    RUNS_TOTAL.labels(status).inc()
    if status != "pending_review":
        RUNS_ACTIVE.set(0)
        RUN_STARTED_AT.set(0)


def set_kill_switch(active: bool) -> None:
    KILL_SWITCH_ACTIVE.set(1 if active else 0)


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