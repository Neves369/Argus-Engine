from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs

import httpx
import respx

from app.scanning.client import ScanHTTPClient
from app.scanning.service import ScanService


def _run(coro):
    return asyncio.run(coro)


_LOGIN_HTML = """<html><body><form action="/authenticate" method="post">
<input type="text" name="csrf" value="tok123"/>
<input type="text" name="username"/>
<input type="password" name="password"/>
<button type="submit">Enter</button>
</form></body></html>"""

_ROOT_HTML = "<html><body>authenticated index</body></html>"


def _service(**kwargs) -> ScanService:
    defaults: dict = {
        "client": ScanHTTPClient(rate_limit=0),
        "respect_robots": False,
        "login_url": "http://example.com/login",
        "login_username": "operator",
        "login_password": "hunter2",
    }
    defaults.update(kwargs)
    return ScanService(**defaults)


@respx.mock
def test_login_posts_credentials_and_reuses_session():
    respx.get("http://example.com/login").mock(return_value=httpx.Response(200, text=_LOGIN_HTML))
    respx.post("http://example.com/authenticate").mock(
        return_value=httpx.Response(
            200, headers={"Set-Cookie": "session=abc123; Path=/; HttpOnly"}
        )
    )
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    report = _run(_service().scan({"name": "example.com", "url": "http://example.com/"}))

    assert report.auth == "login dinâmico aplicado"
    submitted = responses_by_method("POST")[0].request.content.decode()
    fields = parse_qs(submitted)
    assert fields["username"] == ["operator"]
    assert fields["password"] == ["hunter2"]
    assert fields["csrf"] == ["tok123"]

    root = next(c for c in respx.calls if c.request.method == "GET" and c.request.url.path == "/")
    assert "session=abc123" in root.request.headers["Cookie"]
    assert "hunter2" not in root.request.headers["Cookie"]


@respx.mock
def test_login_without_password_field_notes_unauthenticated(caplog):
    html = '<form action="/login" method="post"><input type="text" name="email"/></form>'
    respx.get("http://example.com/login").mock(return_value=httpx.Response(200, text=html))
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    report = _run(_service().scan({"name": "example.com", "url": "http://example.com/"}))

    assert "nenhum form" in report.auth
    root = next(c for c in respx.calls if c.request.method == "GET" and c.request.url.path == "/")
    assert "Cookie" not in root.request.headers


@respx.mock
def test_login_skipped_without_credentials():
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    report = _run(
        _service(login_url="", login_username="", login_password="").scan(
            {"name": "example.com", "url": "http://example.com/"}
        )
    )

    assert report.auth is None
    login_urls = [c for c in respx.calls if "login" in str(c.request.url)]
    assert login_urls == []


@respx.mock
def test_login_post_failure_is_noted_not_fatal():
    respx.get("http://example.com/login").mock(return_value=httpx.Response(200, text=_LOGIN_HTML))
    respx.post("http://example.com/authenticate").mock(return_value=httpx.Response(503))
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    report = _run(_service().scan({"name": "example.com", "url": "http://example.com/"}))

    assert "login falhou" in report.auth
    assert report.pages


@respx.mock
def test_login_page_unreachable_noted():
    respx.get("http://example.com/login").mock(side_effect=httpx.ReadTimeout("slow"))
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    report = _run(_service().scan({"name": "example.com", "url": "http://example.com/"}))

    assert "página indisponível" in report.auth
    assert report.pages


@respx.mock
def test_login_get_form_submits_via_query_string():
    html = (
        '<form method="get"><input type="hidden" name="crumb" value="abc"/>'
        '<input type="text" name="user"/>'
        '<input type="password" name="pass"/></form>'
    )
    respx.get("http://example.com/login").mock(return_value=httpx.Response(200, text=html))
    respx.get(re.compile(r".*user=operator.*")).mock(return_value=httpx.Response(302))
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    report = _run(_service().scan({"name": "example.com", "url": "http://example.com/"}))

    assert report.auth == "login dinâmico aplicado"
    qs = next(c.request.url.query for c in respx.calls if c.request.url.query)
    assert parse_qs(qs.decode())["pass"] == ["hunter2"]


@respx.mock
def test_client_cookie_jar_persists_and_is_host_scoped():
    respx.get("http://a.com/").mock(
        return_value=httpx.Response(200, headers={"Set-Cookie": "session=abc9"})
    )
    respx.get("http://a.com/next").mock(return_value=httpx.Response(200, text="ok"))
    respx.get("http://b.com/").mock(return_value=httpx.Response(200, text="ok"))
    client = ScanHTTPClient(rate_limit=0, cookies="theme=dark")

    _run(client.get_page("http://a.com/"))
    _run(client.get_page("http://b.com/"))
    _run(client.get_page("http://a.com/next"))

    a_next = next(c for c in respx.calls if str(c.request.url) == "http://a.com/next")
    assert a_next.request.headers["Cookie"] == "theme=dark; session=abc9"
    b = next(c for c in respx.calls if str(c.request.url) == "http://b.com/")
    assert b.request.headers["Cookie"] == "theme=dark"


@respx.mock
def test_credentials_never_logged(caplog):
    respx.get("http://example.com/login").mock(return_value=httpx.Response(200, text=_LOGIN_HTML))
    respx.post("http://example.com/authenticate").mock(
        return_value=httpx.Response(200, headers={"Set-Cookie": "session=abc123"})
    )
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    with caplog.at_level("INFO", logger="app.scanning"):
        _run(_service().scan({"name": "example.com", "url": "http://example.com/"}))

    assert "hunter2" not in caplog.text
    assert "operator" not in caplog.text


def responses_by_method(method: str) -> list[respx.models.Response]:
    return [call.response for call in respx.calls if call.request.method == method]