from __future__ import annotations

from app.scanning.detectors import detect_on_page
from app.scanning.service import ScanReport
from app.scanning.spec import TargetPage
from app.services.scan_findings import derive_findings_from_scan

TARGET = "example.com"
BASE = "http://example.com/"


def _page(
    url: str = BASE,
    body: str = "<html><body>ok</body></html>",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> TargetPage:
    return TargetPage(
        url=url, status_code=status_code, headers=headers or {}, body=body
    )


def _ws_findings(page: TargetPage) -> list[dict]:
    return [
        f
        for f in detect_on_page(page)
        if f["title"] == "WebSocket endpoint detectado (upgrade)"
    ]


def test_websocket_detected_via_upgrade_header():
    page = _page(headers={"Upgrade": "websocket", "Connection": "Upgrade"})
    findings = _ws_findings(page)
    assert len(findings) == 1
    assert "header upgrade: websocket" in findings[0]["evidence"]


def test_websocket_detected_via_sec_websocket_accept_header():
    page = _page(headers={"Sec-WebSocket-Accept": "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="})
    findings = _ws_findings(page)
    assert len(findings) == 1


def test_websocket_detected_via_wss_url_in_body():
    page = _page(body='<script>var s = "wss://example.com/socket";</script>')
    findings = _ws_findings(page)
    assert len(findings) == 1
    assert "wss://example.com/socket" in findings[0]["extras"]["websocket_urls"]


def test_websocket_detected_via_new_websocket_ctor():
    page = _page(body="<script>new WebSocket('wss://example.com/ws')</script>")
    findings = _ws_findings(page)
    assert len(findings) == 1
    assert "new WebSocket(...)" in findings[0]["evidence"]


def test_websocket_not_detected_on_normal_page():
    page = _page(body="<html><body>hello world</body></html>")
    assert _ws_findings(page) == []


def test_websocket_aggregated_per_run():
    report = ScanReport(
        target=TARGET,
        pages=[
            _page(BASE, body='<script>new WebSocket("wss://example.com/a")</script>'),
            _page(BASE + "page2", body='<script>new WebSocket("wss://example.com/b")</script>'),
        ],
    )
    findings = derive_findings_from_scan(report)
    aggregated = [f for f in findings if "endpoint(s) WebSocket detectado(s)" in f["title"]]
    assert len(aggregated) == 1
    extras = aggregated[0]["extras"]
    assert extras["endpoint_count"] == 2
    assert {e["url"] for e in extras["endpoints"]} == {
        "wss://example.com/a",
        "wss://example.com/b",
    }
    assert aggregated[0]["category"] == "Aplicação / superfície de API"
    assert aggregated[0]["status"] == "candidate"
