from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from prometheus_client import REGISTRY

from app.metrics import (
    BUILD_INFO,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS,
    KILL_SWITCH_ACTIVE,
    RUN_STARTED_AT,
    RUNS_ACTIVE,
    RUNS_TOTAL,
)

ROOT = Path(__file__).parent.parent.parent

_METRIC_TOKEN = re.compile(r"\bargus_[a-z0-9_]+")


def _normalize(token: str) -> str:
    # Nome canônico: sem `_total` (counter) e sem sufixos de histograma.
    return re.sub(r"_(bucket|count|sum|total)$", "", token)


def _families_in(expr: str) -> set[str]:
    return {_normalize(t) for t in _METRIC_TOKEN.findall(expr)}


# Famílias registradas em app.metrics — os artefatos de observabilidade só
# podem referenciar métricas que o /metrics realmente exporta. Usamos os
# próprios objetos além do collect() porque famílias vazias podem não aparecer.
_KNOWN_FAMILIES = {_normalize(m.name) for m in REGISTRY.collect()} | {
    _normalize(x._name)  # noqa: SLF001
    for x in (
        HTTP_REQUESTS,
        HTTP_REQUEST_DURATION,
        BUILD_INFO,
        RUNS_TOTAL,
        RUNS_ACTIVE,
        RUN_STARTED_AT,
        KILL_SWITCH_ACTIVE,
    )
}


def test_prometheus_config_scrapes_backend():
    config = yaml.safe_load((ROOT / "ops/prometheus/prometheus.yml").read_text())

    assert "argus" in {job["job_name"] for job in config["scrape_configs"]}
    argus_job = next(j for j in config["scrape_configs"] if j["job_name"] == "argus")
    assert argus_job["metrics_path"] == "/metrics"
    targets = argus_job["static_configs"][0]["targets"]
    assert "backend:8000" in targets
    assert "alerting-rules.yml" in " ".join(config["rule_files"])


def test_alerting_rules_reference_registered_metrics():
    rules = yaml.safe_load(
        (ROOT / "ops/prometheus/alerting-rules.yml").read_text()
    )
    groups = rules["groups"]
    assert groups, "grupos de alerta presentes"
    names = []
    for group in groups:
        for rule in group["rules"]:
            assert "expr" in rule, f"alerta {rule.get('alert')} sem expr"
            names.append(rule["alert"])
            assert _families_in(rule["expr"]) <= _KNOWN_FAMILIES, rule["expr"]

    assert "ArgusKillSwitchActive" in names
    assert "ArgusHTTP5xxRate" in names
    assert "ArgusRunActiveTooLong" in names


def test_grafana_dashboard_references_registered_metrics():
    dashboard = json.loads(
        (ROOT / "ops/grafana/dashboards/argus.json").read_text()
    )
    assert dashboard["panels"], "painéis presentes"

    exprs = [t["expr"] for p in dashboard["panels"] for t in p["targets"]]
    assert exprs, "exprs nos painéis"
    for expr in exprs:
        assert _families_in(expr) <= _KNOWN_FAMILIES, expr

    artifacts = (
        ROOT / "ops/grafana/provisioning/datasources/prometheus.yml"
    ).read_text()
    assert "http://prometheus:9090" in artifacts


def test_monitoring_compose_has_core_stack():
    compose = yaml.safe_load(
        (ROOT / "ops/docker-compose.monitoring.yml").read_text()
    )
    services = set(compose["services"])
    assert {"prometheus", "alertmanager", "grafana"} <= services
    assert "argus-prometheus-data" in compose.get("volumes", {})
    assert "argus-grafana-data" in compose.get("volumes", {})
    for service in ("prometheus", "grafana"):
        assert not any(
            mount.startswith("./data") for mount in compose["services"][service]["volumes"]
        )


def test_monitoring_dev_compose_merges_with_base_dev_stack():
    compose = yaml.safe_load(
        (ROOT / "ops/docker-compose.monitoring.dev.yml").read_text()
    )
    # Mesmo projeto do docker-compose.yml base (rede compartilhada: o
    # Prometheus alcança o backend em backend:8000 sem tocar no deploy prod).
    assert compose["name"] == "argus"
    services = compose["services"]
    assert {"prometheus", "alertmanager", "grafana"} <= set(services)
    for service in ("prometheus", "grafana"):
        ports = {
            p if isinstance(p, str) else str(p.get("published", p))
            for p in services[service].get("ports", [])
        }
        assert ports, f"{service} expõe porta local"
    # Dados em volumes nomeados do projeto `argus`, isolados do deploy prod
    # (`argus-prod`); config vem de bind read-only em ./ops.
    assert "argus-prometheus-data" in compose.get("volumes", {})
    assert "argus-grafana-data" in compose.get("volumes", {})
    for service, volume in (
        ("prometheus", "argus-prometheus-data"),
        ("grafana", "argus-grafana-data"),
    ):
        mounts = services[service]["volumes"]
        assert any(volume in m for m in mounts), f"{service} usa volume nomeado"
        assert not any(m.startswith("./data") for m in mounts)


def test_promtail_ships_to_loki_via_docker_discovery():
    config = yaml.safe_load((ROOT / "ops/promtail/config.yml").read_text())
    assert config["clients"][0]["url"].startswith("http://loki:3100")
    scrape = config["scrape_configs"][0]
    assert scrape["docker_sd_configs"]
    assert any(
        s["source_labels"] == ["__meta_docker_container_name"]
        for s in scrape["relabel_configs"]
    )