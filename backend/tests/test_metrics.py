from __future__ import annotations


def _sample_value(body: str, metric: str, labels: dict[str, str]) -> float | None:
    """Extrai o valor de uma amostra Prometheus do corpo em texto plano."""
    want = metric + "{"
    for line in body.splitlines():
        if not line.startswith(want):
            continue
        if all(f'{k}="{v}"' in line for k, v in labels.items()):
            return float(line.rsplit("}", 1)[1].strip())
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