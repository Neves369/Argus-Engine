from __future__ import annotations

import asyncio
import json

import httpx
import respx

from app.core.config import Settings, get_settings
from app.scanning.client import ScanHTTPClient
from app.scanning.service import build_scan_service


def _run(coro):
    return asyncio.run(coro)


@respx.mock
def test_extra_headers_sent_to_target():
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text="ok"))
    client = ScanHTTPClient(
        rate_limit=0,
        extra_headers={"Authorization": "Bearer s3cr3t", "X-Custom": "1"},
    )

    _run(client.get_page("http://example.com/"))

    headers = respx.calls[0].request.headers
    assert headers["Authorization"] == "Bearer s3cr3t"
    assert headers["X-Custom"] == "1"
    assert headers["User-Agent"].startswith("ArgusEngine/")


@respx.mock
def test_cookies_sent_as_single_cookie_header():
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text="ok"))
    client = ScanHTTPClient(rate_limit=0, cookies="session=abc123; theme=dark")

    _run(client.get_page("http://example.com/"))

    assert respx.calls[0].request.headers["Cookie"] == "session=abc123; theme=dark"


@respx.mock
def test_default_client_sends_no_auth_headers():
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text="ok"))
    client = ScanHTTPClient(rate_limit=0)

    _run(client.get_page("http://example.com/"))

    headers = respx.calls[0].request.headers
    assert "Cookie" not in headers
    assert "Authorization" not in headers


@respx.mock
def test_build_scan_service_passes_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "scan_extra_headers", {"Authorization": "Bearer xyz"})
    monkeypatch.setattr(settings, "scan_cookies", "session=abc")
    service = build_scan_service()

    respx.get("http://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(200, text="<html><body>ok</body></html>")
    )
    _run(service.scan({"name": "example.com", "url": "http://example.com/"}))

    headers = respx.calls[0].request.headers
    assert headers["Authorization"] == "Bearer xyz"
    assert headers["Cookie"] == "session=abc"


def test_settings_parse_scan_auth_env(monkeypatch):
    monkeypatch.setenv("SCAN_EXTRA_HEADERS", json.dumps({"X-Test": "1", "X-Other": "2"}))
    monkeypatch.setenv("SCAN_COOKIES", "a=b; c=d")

    settings = Settings(_env_file=None)

    assert settings.scan_extra_headers == {"X-Test": "1", "X-Other": "2"}
    assert settings.scan_cookies == "a=b; c=d"


@respx.mock
def test_headers_never_logged(caplog):
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text="ok"))
    client = ScanHTTPClient(rate_limit=0, extra_headers={"Authorization": "Bearer SUPER-SECRET"})

    with caplog.at_level("INFO", logger="app.scanning.client"):
        _run(client.get_page("http://example.com/"))

    assert "SUPER-SECRET" not in caplog.text