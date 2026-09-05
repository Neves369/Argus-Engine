from __future__ import annotations

from typing import Any

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
) -> dict[str, Any]:
    """Build a candidate finding in the shared report shape.

    Everything here is evidence-grounded: only observed response data is
    recorded, never an inferred value or a fabricated CVE. The finding stays
    ``candidate`` with ``requires_human_review=True`` — scan results are leads
    for a human, not confirmed vulnerabilities.
    """
    return {
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


def _input_vectors(page: TargetPage) -> dict[str, Any] | None:
    """A03 passive lead: forms with editable inputs found on the page.

    Purely observational — no payload is sent. A lead telling the operator
    that user-controlled input surfaces exist and deserve manual review.
    """
    if not page.forms:
        return None
    inputs = [
        f"<{f.method} {f.action}>"
        for f in page.forms
        if any(
            fld.type in ("text", "email", "password", "search", "url", "number")
            for fld in f.fields
        )
    ]
    if not inputs:
        return None
    return _finding(
        title="Formulários com entrada de dados encontrados",
        description=(
            "Páginas do alvo expõem formulários com campos de entrada "
            "(texto/e-mail/senha) e envio a endpoint da aplicação. Esses são "
            "vetores em que o tratamento de entrada precisa ser revisado "
            "manualmente pelo operador — nenhum teste é executado aqui; é "
            "apenas um lead observacional de superfície."
        ),
        severity="info",
        category="A03:2021 Injection (leads passivos)",
        affected=page.host,
        evidence=(
            f"GET {page.url} -> formulários: " + ", ".join(inputs)[:500]
        ),
        remediation=(
            "Revise manualmente o tratamento de entrada destes endpoints "
            "(validação, parametrização e codificação de saída)."
        ),
        confidence=0.5,
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
    _permissive_cors,
)


def detect_on_page(page: TargetPage) -> list[dict[str, Any]]:
    """Run all passive detectors against a single observed page."""
    findings = [fn(page) for fn in _DETECTORS]
    return [f for f in findings if f is not None]