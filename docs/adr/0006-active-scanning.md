# ADR-0006 — Scanning Ativo (OWASP Top 10)

**Status:** Aceito

## Contexto

O Argus Engine foi construído inicialmente como plataforma de orquestração OSINT passivo — consulta de APIs externas (NVD, crt.sh, AbuseIPDB, urlscan.io) para levantar inteligência sobre o alvo. Nenhuma requisição HTTP é enviada ao alvo; o código-fonte de páginas nunca é baixado; o sistema não crawla, não analisa headers de resposta, não extrai forms, não testa vetores de ataque.

Isso resulta em uma plataforma que só encontra vulnerabilidades **já publicadas e indexadas** em feeds externos. Para um alvo com falhas reais (ex.: um lab de vulnerabilidades PHP), nenhum finding é gerado — o sistema é cego para tudo que não esteja nos bancos de dados de terceiros.

Uma plataforma de pentest/bug bounty precisa necessariamente interagir com o alvo para encontrar vulnerabilidades reais. Sem scanning ativo, o Argus Engine é apenas um agregador de OSINT, não um scanner de segurança.

## Decisão

Adicionar **scanning ativo** como funcionalidade core da plataforma, separada do Modo Diabo:

### Scanning Ativo (padrão)
- **Sempre roda** quando o alvo está dentro de `ALLOWED_SCOPES`
- **Não depende** do `DEVIL_MODE`
- Realiza: download de página, análise de headers HTTP, crawl de links/forms, fingerprinting de tecnologias, detecção de vulnerabilidades (OWASP Top 10)
- Sujeito a: rate limiting, timeout, self-imposed restrictions, controles de sandbox
- Findings gerados são evidência-grounded (baseados em respostas HTTP reais do alvo)

### Modo Diabo (separado)
- Modo de execução **sem restrições** para ações destrutivas (futuramente: execução de exploits)
- Exige: escopo validado + sandbox + kill-switch + auditoria + HITL
- **Não é scanning ativo** — é uma camada adicional de execução

### Vetores de scanning (OWASP Top 10)
O scanning ativo cobre, no mínimo:
- A01: Broken Access Control
- A02: Cryptographic Failures (headers TLS, cookies insecure)
- A03: Injection (SQL, XSS, command injection — detecção passiva via forms/parâmetros)
- A04: Insecure Design
- A05: Security Misconfiguration (headers de segurança, diretórios expostos, banners)
- A06: Vulnerable and Outdated Components (fingerprinting de versões)
- A07: Identification and Authentication Failures
- A08: Software and Data Integrity Failures
- A09: Security Logging and Monitoring Failures
- A10: Server-Side Request Forgery (SSRF)

### Controles obrigatórios para scanning ativo
- `ALLOWED_SCOPES` validado antes de qualquer requisição ao alvo
- Rate limiting por target (configurável via `SCAN_RATE_LIMIT`)
- Timeout por requisição (configurável via `SCAN_REQUEST_TIMEOUT`)
- Self-imposed restrictions: respeitar `robots.txt`, não executar payloads destrutivos
- Logging completo de todas as requisições ao alvo
- Kill-switch interrompe scanning em andamento

## Consequências

- O `HermitAgent` ganha capacidade de scanning ativo (download, crawl, análise de resposta) além de OSINT passivo
- Novo módulo `app/scanning/` encapsula a lógica de scanning (HTTP client, parsers, detecção)
- Findings passam a ter evidência de scanning real (respostas HTTP, headers, conteúdo de página)
- Controles de segurança precisam ser expandidos para incluir rate limiting e self-imposed restrictions
- O relatório de segurança ganha dados reais de scanning, não só inteligência de feeds externos
- `docs/SECURITY.md`, `docs/AGENTS.md`, `docs/ROADMAP.md` e demais documentos são atualizados para refletir esta decisão
