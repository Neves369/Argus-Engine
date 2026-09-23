from __future__ import annotations

import pytest

from app.orchestration.compose import validate_sequence
from app.policies.presets import (
    TarotPreset,
    _validate_preset,
    list_presets,
    load_presets,
    resolve_preset,
    run_preset,
)


def test_presets_catalog_loads_all():
    assert set(load_presets()) == {"recon", "app-map", "deep-web", "api"}


def test_all_presets_have_valid_sequence():
    for preset in list_presets():
        assert validate_sequence(preset.archetypes) == preset.archetypes


def test_recon_preset():
    preset = resolve_preset("recon")
    assert preset.archetypes == ["hermit", "justice"]
    assert preset.policy_package == "surface-only"
    assert preset.sha256


def test_app_map_preset():
    preset = resolve_preset("app-map")
    assert preset.archetypes == ["hermit", "fool", "justice"]
    assert preset.policy_package == "surface-only"


def test_deep_web_preset():
    preset = resolve_preset("deep-web")
    assert preset.archetypes == ["hermit", "fool", "justice"]
    assert preset.policy_package == "bugbounty-web"


def test_api_preset():
    preset = resolve_preset("api")
    assert preset.archetypes == ["hermit", "magician", "justice"]
    assert preset.policy_package == "api-only"


def test_resolve_unknown_preset_raises():
    with pytest.raises(KeyError):
        resolve_preset("nope")


def test_run_preset_is_authoritative_for_archetypes():
    policy = run_preset(
        "recon",
        archetypes=["fool", "justice"],
        policy_package=None,
    )
    assert policy["preset"] == "recon"
    assert policy["archetypes"] == ["hermit", "justice"]
    assert policy["policy_package"] == "surface-only"
    assert policy["preset_resolved"]["sha256"]


def test_run_preset_explicit_policy_package_wins():
    policy = run_preset(
        "recon",
        archetypes=["fool", "justice"],
        policy_package="api-only",
    )
    assert policy["archetypes"] == ["hermit", "justice"]
    assert policy["policy_package"] == "api-only"


def test_run_preset_without_preset_passthrough():
    policy = run_preset(
        None,
        archetypes=["fool", "justice"],
        policy_package="lab",
    )
    assert policy["preset"] is None
    assert policy["archetypes"] == ["fool", "justice"]
    assert policy["policy_package"] == "lab"
    assert policy["preset_resolved"] is None


def test_preset_rejects_unknown_policy_package():
    bad = TarotPreset(
        id="x", version="1.0.0", name="x",
        archetypes=["hermit", "justice"], policy_package="does_not_exist",
    )
    with pytest.raises(ValueError):
        _validate_preset(bad)


def test_presets_endpoint(client):
    resp = client.get("/api/v1/presets")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert {"recon", "app-map", "deep-web", "api"} <= ids


def test_preset_endpoint(client):
    resp = client.get("/api/v1/presets/recon")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "recon"
    assert body["archetypes"] == ["hermit", "justice"]
    assert body["policy_package"] == "surface-only"


def test_preset_endpoint_not_found(client):
    assert client.get("/api/v1/presets/nope").status_code == 404
