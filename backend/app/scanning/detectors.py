from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlparse

from app.scanning.parsers import analyze_headers
from app.scanning.spec import TargetPage


def _finding(
    *,
    title: str,
    description: str,
    severity: str,
    category: str,
    affected: str,
    evidence: str,
    remediation: str,
    confidence: float = 0.7,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a candidate finding in the shared report shape.

    Everything here is evidence-grounded: only observed response data is
    recorded, never an inferred value or a fabricated CVE. The finding stays
    ``candidate`` with ``requires_human_review=True`` — scan results are leads
    for a human, not confirmed vulnerabilities.
    """
    finding = {
        "id": None,
        "title": title,
        "description": description,
        "severity": severity,
        "category": category,
        "affected": affected,
        "cvss_score": None,
        "cvss_vector": None,
        "cves": [],
        "known_exploits": [],
        "remediation": remediation,
        "references": ["https://owasp.org/Top10/"],
        "evidence": evidence,
        "confidence": confidence,
        "status": "candidate",
        "requires_human_review": True,
    }
    if extras:
        finding["extras"] = extras
    return finding


def _is_https(url: str) -> bool:
    return str(url).lower().startswith("https://")


def _server_banner(page: TargetPage) -> dict[str, Any] | None:
    """A06/A05 lead: the server discloses its exact version banner."""
    from app.scanning.fingerprint import server_version_banner

    banner = server_version_banner(page)
    if banner is None:
        return None
    return _finding(
        title="Servidor divulga versão exata no header de resposta",
        description=(
            "O alvo expõe a versão exata do servidor web no header HTTP de "
            "resposta. Isso reduz o esforço de identificação da stack por um "
            "atacante e permite correlacionar o alvo a vulnerabilidades "
            "conhecidas dessa versão. A presença da versão é observada aqui; "
            "a correlação a CVE exige validação manual da versão real."
        ),
        severity="info",
        category="A05:2021 Security Misconfiguration",
        affected=page.host,
        evidence=f"GET {page.url} -> Server: {banner}",
        remediation=(
            "Configure o servidor para não divulgar a versão exata no header "
            "Server (ou em banners de componentes atrás do proxy)."
        ),
        confidence=0.8,
    )


def _missing_security_headers(page: TargetPage) -> dict[str, Any] | None:
    """A05 lead: response lacks standard security headers."""
    analysis = analyze_headers(page.headers)
    missing = analysis["security_headers_missing"]
    if not missing:
        return None
    return _finding(
        title="Headers de segurança ausentes na resposta",
        description=(
            "A resposta HTTP não inclui headers de proteção padrão "
            "(Content-Security-Policy, Strict-Transport-Security, "
            "X-Frame-Options, X-Content-Type-Options, Referrer-Policy, "
            "Permissions-Policy), deixando o alvo exposto a classes de ataque "
            "de camada de aplicação. Listado como lead para revisão manual."
        ),
        severity="low",
        category="A05:2021 Security Misconfiguration",
        affected=page.host,
        evidence=f"GET {page.url} -> response sem headers: " + ", ".join(missing),
        remediation=(
            "Adicione os headers de segurança aplicáveis ao tipo de conteúdo "
            "servido (pelo menos CSP, X-Frame-Options, nosniff e HSTS em HTTPS)."
        ),
        confidence=0.75,
    )


def _insecure_cookies(page: TargetPage) -> dict[str, Any] | None:
    """A02/A05 lead: cookies missing Secure/HttpOnly/SameSite flags."""
    analysis = analyze_headers(page.headers)
    insecure = [
        c for c in analysis["cookies"] if not c["secure"] or not c["httponly"] or not c["samesite"]
    ]
    if not insecure:
        return None
    flags = "; ".join(
        f"{c['name']}(secure={c['secure']},httponly={c['httponly']},samesite={c['samesite']})"
        for c in insecure
    )
    return _finding(
        title="Cookies de sessão sem flags de proteção",
        description=(
            "Cookies emitidos pelo alvo carecem de um ou mais flags de proteção "
            "(Secure, HttpOnly, SameSite), o que facilita intercepção em conexão "
            "não criptografada, exposição via script e envio impróprio de "
            "origem cruzada. Listado como lead para revisão manual."
        ),
        severity="low",
        category="A02:2021 Cryptographic Failures",
        affected=page.host,
        evidence=(
            f"GET {page.url} -> Set-Cookie com flags ausentes: {flags}"
        ),
        remediation=(
            "Emita cookies com Secure e HttpOnly, e defina SameSite de acordo "
            "com o uso pretendido (Strict/Lax)."
        ),
        confidence=0.7,
    )


def _missing_hsts(page: TargetPage) -> dict[str, Any] | None:
    """A02 lead: HTTPS endpoint missing HSTS."""
    if not _is_https(page.url):
        return None
    analysis = analyze_headers(page.headers)
    if "strict-transport-security" in analysis["security_headers_present"]:
        return None
    return _finding(
        title="HSTS ausente em endpoint HTTPS",
        description=(
            "O alvo atende em HTTPS mas não emite Strict-Transport-Security, "
            "permitindo rebaixamento de protocolo e exposição da primeira "
            "conexão de um cliente. Listado como lead para revisão manual."
        ),
        severity="low",
        category="A02:2021 Cryptographic Failures",
        affected=page.host,
        evidence=f"GET {page.url} -> HTTPS sem header Strict-Transport-Security",
        remediation="Emita Strict-Transport-Security com max-age adequado em toda resposta HTTPS.",
        confidence=0.7,
    )


_EDITABLE_TYPES = ("text", "email", "password", "search", "url", "number", "file", "tel")
_SENSITIVE_TYPES = ("password", "file", "hidden")
_SENSITIVE_NAME_HINTS = ("token", "csrf", "secret", "apikey", "api_key", "key", "pass", "auth")


def _field_is_sensitive(field) -> bool:
    if field.type in _SENSITIVE_TYPES:
        return True
    name = (field.name or "").lower()
    return any(hint in name for hint in _SENSITIVE_NAME_HINTS)


def _input_vectors(page: TargetPage) -> dict[str, Any] | None:
    """Aplicação passive lead: forms with editable inputs found on the page.

    Purely observational — no payload is sent. A lead telling the operator
    that user-controlled input surfaces exist and deserve manual review. The
    detailed route list (``extras["routes"]``) stays available for the Carro
    to re-prove each form live (Etapa 15/M2); the report level aggregates
    everything into a single per-run finding.
    """
    if not page.forms:
        return None
    routes: list[dict[str, Any]] = []
    for form in page.forms:
        if not any(
            fld.type in _EDITABLE_TYPES or _field_is_sensitive(fld)
            for fld in form.fields
        ):
            continue
        fields = [fld.name for fld in form.fields if fld.name]
        sensitive = [fld.name for fld in form.fields if fld.name and _field_is_sensitive(fld)]
        action = form.action or urlparse(page.url).path
        routes.append(
            {
                "url": page.url,
                "action": action,
                "method": form.method.upper(),
                "fields": fields,
                "sensitive_fields": sensitive,
                "probe_url": page.url,
            }
        )
    if not routes:
        return None
    preview = "; ".join(
        f"<{route['method']} {route['action']}>" for route in routes
    )[:500]
    return _finding(
        title="Formulários com entrada de dados encontrados",
        description=(
            "Páginas do alvo expõem formulários com campos de entrada "
            "(texto/e-mail/senha) e envio a endpoint da aplicação. Esses são "
            "vetores em que o tratamento de entrada precisa ser revisado "
            "manualmente pelo operador — nenhum teste é executado aqui; é "
            "apenas um lead observacional de superfície. O relatório agrega "
            "estes formulários por run; o detalhe por rota fica em extras."
        ),
        severity="info",
        category="Aplicação / vetores de entrada",
        affected=page.host,
        evidence=f"GET {page.url} -> formulários: {preview}",
        remediation=(
            "Revise manualmente o tratamento de entrada destes endpoints "
            "(validação, parametrização e codificação de saída)."
        ),
        confidence=0.5,
        extras={"routes": routes},
    )


def _reflected_parameters(page: TargetPage) -> dict[str, Any] | None:
    """Aplicação passive lead: this page's own URL query params reflecting.

    Only the page's own query string is inspected (never navigation links), so
    repeated nav links are not a source of false positives. A parameter value
    is only reported when it appears clearly as a standalone token in the body
    (word-bounded) and is long enough to be meaningful — a minimum observable
    signal, no payload involved.
    """
    query = urlparse(page.url).query
    if not query:
        return None
    params = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True)]
    if not params:
        return None
    reflected: list[dict[str, Any]] = []
    for name, value in params:
        value = (value or "").strip()
        if len(value) < 3:
            continue
        if re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(value)}(?![A-Za-z0-9_])",
            page.body,
        ):
            reflected.append({"param": name, "value": value})
    if not reflected:
        return None
    summary = "; ".join(f"{r['param']}={r['value']}" for r in reflected)
    return _finding(
        title="Parâmetro refletido no corpo da resposta",
        description=(
            "O valor de um parâmetro da URL consultada aparece integralmente "
            "no corpo da resposta. Isso é um sinal observacional de que a "
            "entrada é refletida sem processamento — um lead para revisão "
            "manual, não uma confirmação de vulnerabilidade (nenhum payload é "
            "enviado). O relatório agrega as reflexões por run."
        ),
        severity="info",
        category="Aplicação / reflexão observada",
        affected=page.host,
        evidence=f"GET {page.url} -> parâmetro(s) refletido(s): {summary}",
        remediation=(
            "Revise manualmente como estes parâmetros são refletidos e "
            "codifique a saída antes de devolver ao navegador."
        ),
        confidence=0.5,
        extras={"reflections": reflected},
    )


_VERBOSE_ERROR_MARKERS = (
    "stack trace",
    "traceback",
    "sql syntax",
    "sqlstate",
    "you have an error in your sql",
    "warning:",
    "notice:",
    "fatal error:",
    "/var/www/",
    "c:\\",
    "undefined index",
    "undefined variable",
    "undefined array key",
    "undefined function",
    "parse error:",
    "syntax error,",
    "pdoexception",
    "deprecated:",
    "microsoft ole db",
    "odbc error",
    "java.lang.",
    "oracle error",
)


def _verbose_error(page: TargetPage) -> dict[str, Any] | None:
    """Aplicação low lead: verbose error markers observed in the response body.

    Classifies what is already in the body (stack trace, SQL syntax errors,
    PHP warnings/notices, on-disk file paths) — no probing or payload. The
    observed markers are recorded as evidence for manual triage.
    """
    lowered = page.body.lower()
    markers = [m for m in _VERBOSE_ERROR_MARKERS if m.lower() in lowered]
    if not markers:
        return None
    path = urlparse(page.url).path or "/"
    return _finding(
        title=f"Erro verboso exposto em {path}",
        description=(
            "A resposta HTTP contém marcadores de erro verboso no corpo "
            "(stack trace, erro de sintaxe SQL, warnings/notices do runtime ou "
            "caminhos de arquivo no disco). Isso pode vazar estrutura interna, "
            "versões de componentes e caminhos do servidor. Classificado aqui "
            "de forma observacional — nenhum teste é executado e nada é "
            "explorado."
        ),
        severity="low",
        category="Aplicação / informação sensível em erro",
        affected=page.host,
        evidence=f"GET {page.url} -> marcadores: " + ", ".join(markers),
        remediation=(
            "Desabilite a exibição de erros detalhados no runtime de produção "
            "e registre os erros apenas no servidor; trate páginas de erro "
            "genéricas para o cliente."
        ),
        confidence=0.6,
        extras={"markers": list(markers)},
    )


_META_REFRESH_RE = re.compile(
    r'<meta[^>]+http-equiv\s*=\s*["\']?refresh["\']?[^>]*>', re.IGNORECASE
)
_META_REFRESH_URL_RE = re.compile(r'url\s*=\s*["\']?([^"\'>\s]+)', re.IGNORECASE)


def _open_redirect_meta(page: TargetPage) -> dict[str, Any] | None:
    """CWE-601 lead: a meta-refresh observed pointing at an external host.

    Observational only — the redirect target is read from the markup already
    returned by the target. No redirect is followed beyond what the client
    already does.
    """
    host = urlparse(page.url).netloc
    for tag in _META_REFRESH_RE.findall(page.body):
        match = _META_REFRESH_URL_RE.search(tag)
        if not match:
            continue
        resolved = urljoin(page.url, match.group(1).strip())
        target_host = urlparse(resolved).netloc
        if target_host and target_host != host:
            return _finding(
                title="Redirecionamento aberto via meta refresh para host externo",
                description=(
                    "A página contém um meta refresh apontando para um host "
                    "diferente do alvo. Se o destino depender de entrada do "
                    "usuário, pode ser um vetor de redirecionamento aberto "
                    "(phishing/roubo de sessão). Registrado como lead observado."
                ),
                severity="low",
                category="CWE-601: URL Redirection to Untrusted Site",
                affected=page.host,
                evidence=f"GET {page.url} -> meta refresh aponta para {resolved}",
                remediation=(
                    "Remova redirecionamentos baseados em URL fornecida pelo "
                    "usuário ou restrinja a uma allowlist de destinos internos."
                ),
                confidence=0.6,
            )
    return None


_DIRECTORY_LISTING_SIGNATURES = (
    "index of /",
    "directory listing for /",
    "parent directory",
    "[to parent directory]",
)


def _directory_listing(page: TargetPage) -> dict[str, Any] | None:
    """A05 lead: the body looks like a generated directory listing."""
    lower = page.body.lower()
    matched = [sig for sig in _DIRECTORY_LISTING_SIGNATURES if sig in lower]
    if not matched:
        return None
    return _finding(
        title="Listagem de diretório exposta",
        description=(
            "O corpo da resposta contém a assinatura de uma listagem de "
            "diretório gerada pelo servidor, expondo a estrutura de arquivos "
            "do alvo. Registrado como lead observado; vale confirmar o que é "
            "realmente público versus o que deveria ser restrito."
        ),
        severity="low",
        category="A05:2021 Security Misconfiguration",
        affected=page.host,
        evidence=f"GET {page.url} -> corpo contém: " + ", ".join(matched),
        remediation=(
            "Desative o autoindex/listing de diretório no servidor web e restrinja "
            "o acesso a diretórios não destinados a público."
        ),
        confidence=0.7,
    )


def _tech_identified(page: TargetPage) -> dict[str, Any] | None:
    """Stack lead: technology identified beyond the Server banner.

    Reports only corroborated signals — technologies matched by observed header
    values or literal body fragments (``page.tech``) plus the ``X-Powered-By``
    header when present. Never a version inferred from nothing.
    """
    analysis = analyze_headers(page.headers)
    signals: list[str] = []
    if page.tech:
        signals.append("tecnologias: " + ", ".join(page.tech))
    if analysis.get("x_powered_by"):
        signals.append(f"X-Powered-By: {analysis['x_powered_by']}")
    if not signals:
        return None
    return _finding(
        title="Stack de tecnologia identificada no alvo",
        description=(
            "A stack de tecnologia do alvo foi identificada a partir de "
            "marcadores observados na resposta (header X-Powered-By e/ou "
            "fragmentos no corpo). É uma pista de superfície para orientar a "
            "correlação a CVEs — não confirma, por si só, versão vulnerável."
        ),
        severity="info",
        category="Superfície de ataque",
        affected=page.host,
        evidence=f"GET {page.url} -> " + "; ".join(signals),
        remediation=(
            "Use a stack identificada para priorizar a revisão manual e a "
            "correlação de versões; minimize a exposição de headers de "
            "framework quando possível."
        ),
        confidence=0.7,
    )


def _permissive_cors(page: TargetPage) -> dict[str, Any] | None:
    """A05 lead: permissive CORS response header."""
    analysis = analyze_headers(page.headers)
    origin = analysis["cors_allow_origin"]
    if origin != "*":
        return None
    return _finding(
        title="CORS permissivo (Access-Control-Allow-Origin: *)",
        description=(
            "O alvo responde com Access-Control-Allow-Origin: *, permitindo que "
            "qualquer origem leia respostas deste recurso em um navegador. "
            "Agravante se combinado a credenciais. Listado como lead para "
            "revisão manual."
        ),
        severity="low",
        category="A05:2021 Security Misconfiguration",
        affected=page.host,
        evidence=f"GET {page.url} -> Access-Control-Allow-Origin: *",
        remediation=(
            "Restrinja Access-Control-Allow-Origin à lista de origens confiáveis "
            "e nunca combine '*' com Access-Control-Allow-Credentials: true."
        ),
        confidence=0.7,
    )


_DETECTORS = (
    _server_banner,
    _missing_security_headers,
    _insecure_cookies,
    _missing_hsts,
    _input_vectors,
    _reflected_parameters,
    _verbose_error,
    _permissive_cors,
    _open_redirect_meta,
    _directory_listing,
    _tech_identified,
)


def detect_on_page(page: TargetPage) -> list[dict[str, Any]]:
    """Run all passive detectors against a single observed page."""
    findings = [fn(page) for fn in _DETECTORS]
    return [f for f in findings if f is not None]