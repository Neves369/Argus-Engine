"""Deterministic demo findings for the simulated scan (no real tools yet).

This is the seam where real tools/APIs (CVE, exploit, OSINT) will plug in. For
now it returns a fixed, safe set of representative security findings so a run
produces a pentest/bug-bounty-shaped report even without integrations.

Findings carry the full report surface (class, severity, CVSS, CVE, known
exploits, remediation, evidence, references). Values are illustrative only —
they do not describe offensive technique and are not tied to a real target.
"""

from __future__ import annotations

from typing import Any


def demo_findings(target: str) -> list[dict[str, Any]]:
    target = target or "unknown"
    return [
        {
            "id": "F-1",
            "title": "Versão desatualizada do servidor web exposta (Apache 2.4.49)",
            "description": (
                "O servidor divulga sua versão exata no header de resposta, o que "
                "permite correlacionar o alvo a vulnerabilidades conhecidas dessa "
                "versão sem nenhuma autenticação."
            ),
            "severity": "critical",
            "category": "A06:2021 Vulnerable and Outdated Components",
            "affected": "Apache HTTP Server 2.4.49",
            "cvss_score": 7.5,
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
            "cves": ["CVE-2021-41773"],
            "known_exploits": ["Public PoC disponível (Exploit-DB 50383)"],
            "remediation": "Atualize o Apache HTTP Server para 2.4.51 ou posterior.",
            "references": ["https://httpd.apache.org/security/vulnerabilities_24.html"],
            "evidence": f"Server: Apache/2.4.49 (Ubuntu) em {target}",
            "confidence": 0.9,
            "status": "candidate",
            "requires_human_review": False,
        },
        {
            "id": "F-2",
            "title": "Protocolos TLS legados habilitados (TLS 1.0/1.1)",
            "description": (
                "O alvo ainda aceita versões legadas do TLS, sujeitas a ataques de "
                "rebaixamento e sem os controles criptográficos exigidos por padrões "
                "atuais."
            ),
            "severity": "medium",
            "category": "A02:2021 Cryptographic Failures",
            "affected": f"{target} (endpoint TLS)",
            "cvss_score": 5.9,
            "cvss_vector": "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N",
            "cves": [],
            "known_exploits": [],
            "remediation": "Desabilite TLS 1.0 e 1.1 e exija TLS 1.2 ou superior.",
            "references": ["https://owasp.org/Top10/A02_2021-Cryptographic_Failures/"],
            "evidence": f"{target} respondeu a handshake com TLSv1.0 e TLSv1.1",
            "confidence": 0.85,
            "status": "candidate",
            "requires_human_review": False,
        },
        {
            "id": "F-3",
            "title": "Headers de segurança ausentes",
            "description": (
                "As respostas HTTP não incluem headers de proteção, deixando o alvo "
                "exposto a clickjacking, sniffing de MIME e outras classes de ataque "
                "de camada de aplicação."
            ),
            "severity": "low",
            "category": "A05:2021 Security Misconfiguration",
            "affected": f"{target}",
            "cvss_score": None,
            "cvss_vector": None,
            "cves": [],
            "known_exploits": [],
            "remediation": (
                "Adicione Content-Security-Policy, X-Frame-Options: DENY, "
                "X-Content-Type-Options: nosniff e Strict-Transport-Security."
            ),
            "references": ["https://owasp.org/www-project-secure-headers/"],
            "evidence": f"Resposta de {target} sem Content-Security-Policy / X-Frame-Options",
            "confidence": 0.8,
            "status": "candidate",
            "requires_human_review": False,
        },
    ]


def demo_executed_finding(target: str) -> dict[str, Any]:
    """Single rich finding recorded after an approved execution (devil mode)."""
    target = target or "unknown"
    return {
        "id": None,
        "title": f"Executed action for {target}",
        "description": (
            "A ação aprovada pelo operador foi executada e seu resultado foi "
            "registrado para auditoria. O detalhe operacional não é registrado aqui."
        ),
        "severity": "high",
        "category": "A01:2021 Broken Access Control",
        "affected": target,
        "cvss_score": None,
        "cvss_vector": None,
        "cves": [],
        "known_exploits": [],
        "remediation": "Revise o controle de acesso do recurso afetado.",
        "references": [],
        "evidence": f"Ação confirmada contra {target}",
        "confidence": 0.9,
        "status": "candidate",
        "requires_human_review": False,
    }
