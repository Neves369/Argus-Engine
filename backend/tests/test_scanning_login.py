from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs

import httpx
import respx

from app.scanning.client import ScanHTTPClient
from app.scanning.service import ScanService
from app.services.scan_findings import derive_findings_from_scan


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


@respx.mock
def test_login_labels_pages_as_user_session_and_records_metadata():
    respx.get("http://example.com/login").mock(return_value=httpx.Response(200, text=_LOGIN_HTML))
    respx.post("http://example.com/authenticate").mock(
        return_value=httpx.Response(200, headers={"Set-Cookie": "session=abc123; Path=/"})
    )
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    report = _run(_service().scan({"name": "example.com", "url": "http://example.com/"}))

    assert all(page.session == "user" for page in report.pages)
    assert report.sessions == [
        {
            "name": "user",
            "auth_status": "success",
            "auth": "login dinâmico aplicado",
            "auth_cookies": ["session"],
            "page_count": 1,
        }
    ]
    assert report.anon_probe == [
        {"url": "http://example.com/", "status_code": 200, "final_url": "http://example.com/"}
    ]
    titles = [f["title"] for f in derive_findings_from_scan(report)]
    assert not any("apenas em sessão autenticada" in t for t in titles)


@respx.mock
def test_without_login_pages_are_anonymous_session():
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    report = _run(
        _service(login_url="", login_username="", login_password="").scan(
            {"name": "example.com", "url": "http://example.com/"}
        )
    )

    assert all(page.session == "anon" for page in report.pages)
    assert report.sessions[0]["name"] == "anon"
    assert report.sessions[0]["auth_status"] == "skipped"
    assert report.sessions[0]["page_count"] == 1
    assert report.anon_probe == []


@respx.mock
def test_failed_login_degrades_to_anonymous_without_baseline():
    respx.get("http://example.com/login").mock(return_value=httpx.Response(200, text=_LOGIN_HTML))
    respx.post("http://example.com/authenticate").mock(return_value=httpx.Response(503))
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=_ROOT_HTML))

    report = _run(_service().scan({"name": "example.com", "url": "http://example.com/"}))

    assert all(page.session == "anon" for page in report.pages)
    assert report.sessions[0]["name"] == "anon"
    assert report.sessions[0]["auth_status"] == "failed"
    assert report.anon_probe == []


def _anon_vs_authed(request):
    if "session=abc123" in (request.headers.get("Cookie") or ""):
        return httpx.Response(200, text=_ROOT_HTML)
    return httpx.Response(302, headers={"Location": "/login"})


@respx.mock
def test_access_difference_finding_when_anonymous_baseline_is_blocked():
    respx.get("http://example.com/login").mock(return_value=httpx.Response(200, text=_LOGIN_HTML))
    respx.post("http://example.com/authenticate").mock(
        return_value=httpx.Response(200, headers={"Set-Cookie": "session=abc123; Path=/"})
    )
    respx.get("http://example.com/").mock(side_effect=_anon_vs_authed)

    report = _run(_service().scan({"name": "example.com", "url": "http://example.com/"}))

    assert report.anon_probe == [
        {"url": "http://example.com/", "status_code": 200, "final_url": "http://example.com/login"}
    ]
    findings = derive_findings_from_scan(report)
    access = [f for f in findings if "apenas em sessão autenticada" in f["title"]]
    assert len(access) == 1
    assert access[0]["category"] == "Aplicação / controle de acesso"
    assert access[0]["status"] == "candidate"
    extras = access[0]["extras"]
    assert extras["asymmetric"][0]["url"] == "http://example.com/"
    assert extras["asymmetric"][0]["anon_status"] == 200
    assert extras["asymmetric"][0]["anon_final_url"] == "http://example.com/login"
    assert extras["asymmetric"][0]["auth_status"] == 200


_MULTI_PROFILES = [
    {
        "name": "admin",
        "login_url": "http://example.com/login",
        "username": "admin",
        "password": "admin-secret",
    },
    {
        "name": "operator",
        "login_url": "http://example.com/login",
        "username": "operator",
        "password": "op-secret",
    },
]


def _multi_service(**kwargs) -> ScanService:
    defaults: dict = {
        "client": ScanHTTPClient(rate_limit=0),
        "respect_robots": False,
        "login_url": "",
        "login_username": "",
        "login_password": "",
        "session_profiles": _MULTI_PROFILES,
        "client_factory": lambda: ScanHTTPClient(rate_limit=0),
    }
    defaults.update(kwargs)
    return ScanService(**defaults)


def _cookie_aware_login(request):
    content = request.content.decode()
    if "admin" in content:
        return httpx.Response(200, headers={"Set-Cookie": "admin=1; Path=/"})
    return httpx.Response(200, headers={"Set-Cookie": "op=1; Path=/"})


def _cookie_aware_root(request):
    cookie = request.headers.get("Cookie") or ""
    if "admin=1" in cookie:
        return httpx.Response(200, text="<html><body>admin panel</body></html>")
    if "op=1" in cookie:
        return httpx.Response(404, text="not found")
    return httpx.Response(302, headers={"Location": "/login"})


@respx.mock
def test_multiple_session_profiles_crawl_isolated_and_report_cross_session_diff():
    respx.get("http://example.com/login").mock(
        return_value=httpx.Response(200, text=_LOGIN_HTML)
    )
    respx.post("http://example.com/authenticate").mock(side_effect=_cookie_aware_login)
    respx.get("http://example.com/").mock(side_effect=_cookie_aware_root)

    report = _run(
        _multi_service().scan({"name": "example.com", "url": "http://example.com/"})
    )

    assert {p.session for p in report.pages} == {"admin", "operator"}
    assert report.sessions == [
        {
            "name": "admin",
            "auth_status": "success",
            "auth": "login dinâmico aplicado",
            "auth_cookies": ["admin"],
            "page_count": 1,
        },
        {
            "name": "operator",
            "auth_status": "success",
            "auth": "login dinâmico aplicado",
            "auth_cookies": ["op"],
            "page_count": 1,
        },
    ]
    assert report.anon_probe == [
        {
            "url": "http://example.com/",
            "status_code": 200,
            "final_url": "http://example.com/login",
        }
    ]

    findings = derive_findings_from_scan(report)
    admin_only = [f for f in findings if "apenas na sessão admin" in f["title"]]
    assert len(admin_only) == 1
    assert admin_only[0]["extras"]["asymmetric"][0]["session"] == "admin"
    cross = [f for f in findings if "Acesso distinto entre sessões" in f["title"]]
    assert len(cross) == 1
    assert cross[0]["extras"]["routes"] == [
        {"url": "http://example.com/", "accessible_in": ["admin"], "not_in": ["operator"]}
    ]


@respx.mock
def test_secondary_profile_failed_login_degrades_and_is_excluded():
    respx.get("http://example.com/login").mock(
        return_value=httpx.Response(200, text=_LOGIN_HTML)
    )

    def _login_admin_only(request):
        content = request.content.decode()
        if "admin" in content:
            return httpx.Response(200, headers={"Set-Cookie": "admin=1; Path=/"})
        return httpx.Response(503)

    respx.post("http://example.com/authenticate").mock(side_effect=_login_admin_only)
    respx.get("http://example.com/").mock(side_effect=_cookie_aware_root)

    report = _run(
        _multi_service().scan({"name": "example.com", "url": "http://example.com/"})
    )

    statuses = {s["name"]: s["auth_status"] for s in report.sessions}
    assert statuses == {"admin": "success", "operator": "failed"}
    findings = derive_findings_from_scan(report)
    assert any("na sessão admin" in f["title"] for f in findings)
    assert not any("Acesso distinto entre sessões" in f["title"] for f in findings)


def test_scan_service_skips_incomplete_session_profiles():
    service = ScanService(
        client=ScanHTTPClient(rate_limit=0),
        session_profiles=[
            {
                "name": "admin",
                "login_url": "http://example.com/login",
                "username": "root",
                "password": "p",
            },
            {"name": "broken"},
        ],
    )

    assert len(service._session_profiles) == 1
    assert service._session_profiles[0]["name"] == "admin"


def responses_by_method(method: str) -> list[respx.models.Response]:
    return [call.response for call in respx.calls if call.request.method == method]