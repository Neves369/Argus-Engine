from __future__ import annotations

from app.metrics import record_run_start, record_run_terminal, set_kill_switch


def _sample_value(body: str, metric: str, labels: dict[str, str]) -> float | None:
    """Extrai o valor de uma amostra Prometheus do corpo em texto plano."""
    want = metric + "{"
    for line in body.splitlines():
        if not line.startswith(want):
            continue
        if all(f'{k}="{v}"' in line for k, v in labels.items()):
            return float(line.rsplit("}", 1)[1].strip())
    return None


def _gauge_value(body: str, metric: str) -> float | None:
    for line in body.splitlines():
        if line.startswith(metric) and "{" not in line.split()[0]:
            return float(line.split()[-1])
    return None


def test_metrics_exposes_prometheus_format(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text
    assert "argus_http_requests_total" in body
    assert "argus_http_request_duration_seconds" in body
    assert 'argus_build_info{app="Argus Engine"} 1.0' in body
    assert 'METRICS_PATH' not in body


def test_metrics_count_requests_and_skips_itself(client):
    before = client.get("/metrics")

    client.get("/health")
    client.get("/health")
    after = client.get("/metrics")

    got = _sample_value(
        before.text,
        "argus_http_requests_total",
        {"method": "GET", "path": "/health", "status": "200"},
    )
    end = _sample_value(
        after.text,
        "argus_http_requests_total",
        {"method": "GET", "path": "/health", "status": "200"},
    )
    # O contador começa vazio (sem amostras); o primeiro /metrics do teste pode
    # ocorrer antes de qualquer requisição /health na sessão.
    assert (got or 0) + 2 == end

    self_metric = _sample_value(
        after.text,
        "argus_http_requests_total",
        {"method": "GET", "path": "/metrics", "status": "200"},
    )
    assert self_metric is None


def test_metrics_records_errors(client):
    start = client.get("/metrics")
    client.get("/api/v1/nao-existe-xyz")
    end = client.get("/metrics")

    got = _sample_value(
        start.text,
        "argus_http_requests_total",
        {"method": "GET", "path": "/api/v1/nao-existe-xyz", "status": "404"},
    )
    final = _sample_value(
        end.text,
        "argus_http_requests_total",
        {"method": "GET", "path": "/api/v1/nao-existe-xyz", "status": "404"},
    )
    assert (got or 0) + 1 == final


def test_metrics_records_run_lifecycle_and_kill_switch(client):
    set_kill_switch(True)
    record_run_start(1_234.0)

    active = client.get("/metrics")
    assert _gauge_value(active.text, "argus_kill_switch_active") == 1
    assert _gauge_value(active.text, "argus_runs_active") == 1
    assert _gauge_value(active.text, "argus_run_started_at_seconds") == 1_234.0

    record_run_terminal("completed")
    done = client.get("/metrics")
    assert _gauge_value(done.text, "argus_runs_active") == 0
    assert _gauge_value(done.text, "argus_run_started_at_seconds") == 0
    assert _sample_value(
        done.text, "argus_runs_total", {"status": "completed"}
    )

    set_kill_switch(False)


def test_metrics_runs_total_counts_and_pending_keeps_active(client):
    record_run_start(500.0)
    record_run_terminal("pending_review")

    body = client.get("/metrics").text
    assert _gauge_value(body, "argus_runs_active") == 1
    assert _gauge_value(body, "argus_run_started_at_seconds") == 500.0
    assert _sample_value(body, "argus_runs_total", {"status": "pending_review"})