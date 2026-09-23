from __future__ import annotations

import pytest

from app.policies.packages import (
    PolicyPackage,
    _validate_references,
    apply_package,
    list_packages,
    load_packages,
    resolve_package,
    run_policy,
)


def test_packages_catalog_loads_all():
    assert set(load_packages()) == {"lab", "bugbounty-web", "api-only", "surface-only"}


def test_lab_resolves_deep_with_all_behavior_probes():
    pkg = resolve_package("lab")
    assert pkg.depth == "deep"
    assert "reflection_p0" in pkg.probe_classes
    assert "authn_p3" in pkg.probe_classes
    assert set(pkg.journey_classes) == {"admin_area_p0", "account_self_p1"}
    assert pkg.sha256


def test_surface_only_is_quick_without_probes():
    pkg = resolve_package("surface-only")
    assert pkg.depth == "quick"
    assert pkg.probe_classes == []
    assert pkg.journey_classes == []


def test_api_only_targets_api_probes():
    pkg = resolve_package("api-only")
    assert pkg.depth == "deep"
    assert pkg.probe_classes == [
        "api_json_error_p0",
        "api_bulk_p1",
        "graphql_introspection_p1",
    ]
    assert pkg.journey_classes == []


def test_bugbounty_web_excludes_stateful_and_authn():
    pkg = resolve_package("bugbounty-web")
    assert "csrf_p2" not in pkg.probe_classes
    assert "authn_p3" not in pkg.probe_classes
    assert "redirect_p2" in pkg.probe_classes


def test_resolve_unknown_package_raises():
    with pytest.raises(KeyError):
        resolve_package("nope")


def test_list_packages_resolves_all():
    assert {p.id for p in list_packages()} == {
        "lab",
        "bugbounty-web",
        "api-only",
        "surface-only",
    }


def test_apply_package_feeds_graph_state():
    applied = apply_package("lab")
    assert applied["policy_package"] == "lab"
    assert applied["depth"] == "deep"
    assert "authn_p3" in applied["probe_classes"]
    assert applied["policy_resolved"]["sha256"]
    assert applied["devil_mode"] is False


def test_run_policy_package_is_authoritative():
    policy = run_policy(
        "surface-only",
        depth="deep",
        probe_classes=["reflection_p0"],
        journey_classes=["admin_area_p0"],
        devil_mode=True,
    )
    assert policy["depth"] == "quick"
    assert policy["probe_classes"] is None
    assert policy["devil_mode"] is False


def test_run_policy_without_package_passthrough():
    policy = run_policy(
        None,
        depth="deep",
        probe_classes=["reflection_p0"],
        journey_classes=None,
        devil_mode=False,
    )
    assert policy["depth"] == "deep"
    assert policy["probe_classes"] == ["reflection_p0"]
    assert policy["policy_package"] is None
    assert policy["policy_resolved"] is None


def test_package_rejects_unknown_probe_class():
    bad = PolicyPackage(
        id="x", version="1.0.0", name="x", probe_classes=["does_not_exist"]
    )
    with pytest.raises(ValueError):
        _validate_references(bad)


def test_package_rejects_unknown_journey():
    bad = PolicyPackage(
        id="x", version="1.0.0", name="x", journey_classes=["does_not_exist"]
    )
    with pytest.raises(ValueError):
        _validate_references(bad)


def test_policy_packages_endpoint(client):
    resp = client.get("/api/v1/policy/packages")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert {"lab", "bugbounty-web", "api-only", "surface-only"} <= ids


def test_policy_package_endpoint(client):
    resp = client.get("/api/v1/policy/packages/lab")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "lab"
    assert body["depth"] == "deep"
    assert "authn_p3" in body["probe_classes"]


def test_policy_package_endpoint_not_found(client):
    assert client.get("/api/v1/policy/packages/nope").status_code == 404
