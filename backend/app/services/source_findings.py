"""Derive genuine, evidence-grounded findings from real data-source results.

Replaces the old placeholder that fabricated the same 3 findings (with a real
CVE ID attached) for every single run, regardless of target — a serious
problem for a security tool: a report claiming a specific vulnerability that
was never actually checked is worse than no report at all (false confidence,
wasted remediation effort, or reputational risk if shared externally).

Every finding produced here must trace back to an actual field in an actual
source response (see `_EXTRACTORS`). Findings are always `status="candidate"`
and `requires_human_review=True` — this module flags *leads* worth a human's
attention, it never asserts a confirmed vulnerability. An unrecognized or
partial response shape is silently skipped rather than guessed at; this
module never fabricates a value to fill a gap.
"""

from __future__ import annotations

from typing import Any


def _abuseipdb_finding(target: str, data: dict[str, Any]) -> dict[str, Any] | None:
    payload = data.get("data")
    if not isinstance(payload, dict):
        return None
    score = payload.get("abuseConfidenceScore")
    if not isinstance(score, int | float) or score < 25:
        return None  # low/no signal — not worth surfacing to a human
    reports = payload.get("totalReports")
    severity = "high" if score >= 75 else "medium" if score >= 50 else "low"
    return {
        "id": None,
        "title": f"IP {target} com histórico de abuso reportado (confiança {score:.0f}%)",
        "description": (
            f"AbuseIPDB registra {reports if reports is not None else 'algum(ns)'} "
            f"reporte(s) para este IP, com confiança de abuso de {score:.0f}%. "
            "Isso não confirma comprometimento do alvo em si — pode refletir "
            "reputação de um IP compartilhado (NAT/CDN/proxy) ou atividade "
            "anterior não relacionada ao uso atual."
        ),
        "severity": severity,
        "category": "Reputação de rede",
        "affected": target,
        "cvss_score": None,
        "cvss_vector": None,
        "cves": [],
        "known_exploits": [],
        "remediation": (
            "Confirme se o IP está sob seu controle direto; se estiver, investigue "
            "a causa dos reportes. Se for um IP compartilhado (CDN/NAT), o reporte "
            "pode não ser atribuível ao seu serviço."
        ),
        "references": [f"https://www.abuseipdb.com/check/{target}"],
        "evidence": f"AbuseIPDB: abuseConfidenceScore={score}, totalReports={reports}",
        "confidence": round(min(0.5 + score / 200, 0.95), 2),
        "status": "candidate",
        "requires_human_review": True,
    }


def _crtsh_finding(target: str, data: dict[str, Any]) -> dict[str, Any] | None:
    payload = data.get("response")
    if not isinstance(payload, list) or not payload:
        return None
    subdomains: set[str] = set()
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        for line in str(entry.get("name_value") or "").splitlines():
            candidate = line.strip().lower()
            if candidate and candidate != target.lower():
                subdomains.add(candidate)
    if not subdomains:
        return None
    ordered = sorted(subdomains)
    sample = ordered[:15]
    more = f" (+{len(ordered) - len(sample)} outro(s))" if len(ordered) > len(sample) else ""
    return {
        "id": None,
        "title": f"{len(ordered)} subdomínio(s) encontrados via certificate transparency",
        "description": (
            "Registros públicos de certificado (crt.sh) revelam nomes de host "
            "adicionais associados a este domínio. Cada um amplia a superfície "
            "exposta e vale confirmar se está mesmo em uso, autorizado, e com o "
            "mesmo nível de proteção do domínio principal."
        ),
        "severity": "info",
        "category": "Superfície de ataque",
        "affected": target,
        "cvss_score": None,
        "cvss_vector": None,
        "cves": [],
        "known_exploits": [],
        "remediation": (
            "Para cada subdomínio: confirme se está ativo e autorizado; desative "
            "os que não estiverem mais em uso (reduz a superfície de ataque)."
        ),
        "references": [f"https://crt.sh/?q={target}"],
        "evidence": "Subdomínios: " + ", ".join(sample) + more,
        "confidence": 0.7,
        "status": "candidate",
        "requires_human_review": True,
    }


def _nvd_finding(target: str, data: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    vulnerabilities = data.get("vulnerabilities")
    if not isinstance(vulnerabilities, list) or not vulnerabilities:
        return None
    cve_ids: list[str] = []
    for item in vulnerabilities[:10]:
        cve = (item or {}).get("cve") if isinstance(item, dict) else None
        cve_id = (cve or {}).get("id") if isinstance(cve, dict) else None
        if isinstance(cve_id, str):
            cve_ids.append(cve_id)
    if not cve_ids:
        return None
    total = data.get("totalResults", len(cve_ids))
    return {
        "id": None,
        "title": f"{len(cve_ids)} CVE(s) retornado(s) pela busca por palavra-chave no NVD",
        "description": (
            "A busca por palavra-chave no NVD (NIST) para o termo do alvo "
            "retornou os CVEs listados abaixo. Isso É UMA CORRESPONDÊNCIA "
            "TEXTUAL, não uma confirmação de que o alvo usa o software afetado "
            "— precisa ser validado manualmente contra a stack real em uso "
            "antes de qualquer ação."
        ),
        "severity": "info",
        "category": "Leads de vulnerabilidade (não confirmado)",
        "affected": target,
        "cvss_score": None,
        "cvss_vector": None,
        "cves": cve_ids,
        "known_exploits": [],
        "remediation": (
            "Valide manualmente se algum destes CVEs se aplica à stack real do "
            "alvo (versão de software confirmada) antes de qualquer remediação."
        ),
        "references": ["https://nvd.nist.gov/vuln/search"],
        "evidence": f"NVD keywordSearch retornou {total} resultado(s) totais para o termo",
        "confidence": 0.4,
        "status": "candidate",
        "requires_human_review": True,
    }


def _urlscan_finding(target: str, data: dict[str, Any]) -> dict[str, Any] | None:
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    total = data.get("total", len(results))
    malicious = sum(
        1
        for result in results
        if isinstance(result, dict)
        and (result.get("verdicts") or {}).get("overall", {}).get("malicious") is True
    )
    sample_urls: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        url = (result.get("task") or {}).get("url") or (result.get("page") or {}).get("url")
        if isinstance(url, str) and url not in sample_urls:
            sample_urls.append(url)
    severity = "low" if malicious else "info"
    return {
        "id": None,
        "title": f"{total} avaliação(ões) pública(s) do domínio {target} no urlscan.io",
        "description": (
            "urlscan.io mantém histórico público de avaliações indexando este "
            "domínio. Isso não confirma vulnerabilidade — apenas indica que o "
            "domínio já foi observado/avaliado publicamente. "
            + (
                f"{malicious} avaliação(ões) foi(ram) marcada(s) como maliciosa(s) "
                "pelo veredito agregado do urlscan.io."
                if malicious
                else "Nenhuma avaliação marcada como maliciosa pelo veredito agregado."
            )
        ),
        "severity": severity,
        "category": "Superfície de ataque",
        "affected": target,
        "cvss_score": None,
        "cvss_vector": None,
        "cves": [],
        "known_exploits": [],
        "remediation": (
            "Revise o conteúdo das avaliações públicas para confirmar se "
            "expõem informação sensível do domínio e se os achados ainda são "
            "relevantes na configuração atual."
        ),
        "references": [f"https://urlscan.io/domain/{target}"],
        "evidence": (
            "urlscan.io: " + "; ".join(sample_urls[:5]) or f"{total} avaliação(ões)"
        ),
        "confidence": 0.5,
        "status": "candidate",
        "requires_human_review": True,
    }


def _ip_api_finding(target: str, data: dict[str, Any]) -> dict[str, Any] | None:
    is_proxy = data.get("proxy") is True
    is_hosting = data.get("hosting") is True
    if not (is_proxy or is_hosting):
        return None
    org = str(data.get("org") or "").strip()
    isp = str(data.get("isp") or "").strip()
    roles = []
    if is_proxy:
        roles.append("proxy")
    if is_hosting:
        roles.append("data center")
    return {
        "id": None,
        "title": f"IP {target} atrás de {'/'.join(roles)}",
        "description": (
            "A geolocalização (ip-api.com) indica que o IP é servido por "
            "proxy ou data center. Isso não é vulnerabilidade em si, mas muda "
            "a interpretação de outros sinais: reputação de IP compartilhado, "
            "WAF/proxy de borda e controles de rede intermediários."
        ),
        "severity": "info",
        "category": "Reputação de rede",
        "affected": target,
        "cvss_score": None,
        "cvss_vector": None,
        "cves": [],
        "known_exploits": [],
        "remediation": (
            "Considere o papel de proxy/data center ao interpretar outros "
            "achados sobre este IP e confirme a cadeia real de serviço."
        ),
        "references": ["https://ip-api.com/"],
        "evidence": f"ip-api.com: proxy={is_proxy}, hosting={is_hosting}, "
        f"isp={isp or 'n/a'}, org={org or 'n/a'}",
        "confidence": 0.7,
        "status": "candidate",
        "requires_human_review": True,
    }


#: Only sources with a verified, stable response shape get a finding
#: extractor. Every other configured source (cve_report, and any
#: future/operator-added source) still gets queried and its raw result
#: kept in `state.sources` for the report/context — it just doesn't (yet)
#: have logic here to turn it into a `findings` entry (cve_report is
#: enriched inside the CVE-correlation service instead).
_EXTRACTORS = {
    "abuseipdb": _abuseipdb_finding,
    "crtsh": _crtsh_finding,
    "nvd": _nvd_finding,
    "urlscan": _urlscan_finding,
    "ip_api": _ip_api_finding,
}


def derive_findings_from_sources(
    target: str, sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Turn real, successfully-fetched source results into genuine findings.

    Simulated results (no API key configured, source unreachable, rate
    limited, ...) are skipped outright — there is no real data to ground a
    finding in, so producing one would just be fabrication with extra steps.
    """
    findings: list[dict[str, Any]] = []
    for result in sources:
        if not isinstance(result, dict) or result.get("status") not in ("ok", "cache"):
            continue
        extractor = _EXTRACTORS.get(result.get("source"))
        if extractor is None:
            continue
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        finding = extractor(target, data)
        if finding is not None:
            findings.append(finding)
    return findings
