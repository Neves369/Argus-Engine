# Política de Segurança

## Uso autorizado

O **Argus Engine** é uma plataforma de **pentest e bug bounty autorizada** com scanning
ativo e orquestração de agentes. O uso é permitido somente em:

- alvos com **autorização explícita** do dono do ativo;
- **escopo definido** e documentado;
- conformidade com **leis locais** e políticas de bug bounty.

Qualquer outro uso é proibido e de responsabilidade exclusiva do usuário.

## Controles de segurança da plataforma

A plataforma implementa controles que não devem ser desativados:

| Controle | Descrição |
|---|---|
| Validação de escopo | `validate_scope` recusa alvos fora da allowlist (`ALLOWED_SCOPES`). |
| Kill-switch | `KILL_SWITCH` + flag runtime interrompem qualquer run. |
| Sandbox | Execução de tools `kind: cli` isolada (Docker descartável, `--network=none`, read-only, cap-drop ALL, usuário não-root — Etapa 5). Opt-in via `TOOL_SANDBOX=true`; **fail-closed**: sem Docker, a tool não roda. Sem sandbox, tools CLI rodam com timeout, rate limit e limites de recurso. |
| Auditoria | Logging estruturado e histórico de decisões persistido. |
| HITL | Aprovação humana obrigatória em ações destrutivas (Modo Diabo). |
| Auth da UI | Senha única de operador + cookie de sessão assinado (HMAC, HttpOnly, SameSite=Lax). |
| Scanning ativo | Rate limiting, timeout, self-imposed restrictions, logging de todas as requisições ao alvo. |

## Scanning Ativo

O scanning ativo (download de página, crawl, análise de headers/forms, detecção de
vulnerabilidades OWASP Top 10) é funcionalidade **core** da plataforma — sempre roda
quando o alvo está dentro de `ALLOWED_SCOPES`, **independentemente do Modo Diabo**.

Controles de scanning ativo:
- `ALLOWED_SCOPES` validado antes de qualquer requisição ao alvo
- Rate limiting por target (`SCAN_RATE_LIMIT`, configurável)
- Timeout por requisição (`SCAN_REQUEST_TIMEOUT`, configurável)
- Limite de páginas por scan (`SCAN_MAX_PAGES`) e de corpo por resposta (`SCAN_MAX_BODY_BYTES`)
- Self-imposed restrictions: respeitar `robots.txt` (`SCAN_RESPECT_ROBOTS`), não executar payloads destrutivos
- User-Agent identificável (`SCAN_USER_AGENT`) em todas as requisições ao alvo
- Auth **opcional** por env: estática (`SCAN_EXTRA_HEADERS`/`SCAN_COOKIES`) ou login dinâmico de
  form (`SCAN_LOGIN_URL`/`SCAN_LOGIN_USERNAME`/`SCAN_LOGIN_PASSWORD`). Credenciais ficam no ambiente,
  não entram em log/relatório (o log do scan registra apenas url/host/status/bytes) e a inspeção
  visual do relatório marca quando o login falhou (`report.auth`) — nunca assume sessão quando não houve.
- Logging completo de todas as requisições ao alvo
- Kill-switch interrompe scanning em andamento

O scanning ativo NÃO é Modo Diabo — é funcionalidade padrão da plataforma. Ver
`docs/adr/0006-active-scanning.md`.

## Modo Diabo

O `DEVIL_MODE` habilita a execução **sem restrições** de scripts invasivos/destrutivos
(futuramente: exploits). É uma camada **separada** do scanning ativo. Mesmo ativo,
permanecem obrigatórios: escopo validado, sandbox, kill-switch, auditoria completa e HITL.

## Autenticação da interface

A UI não tem contas de usuário: há uma **senha única de operador** (`UI_PASSWORD`).
Quando definida, `POST /api/v1/auth/login` emite um cookie `argus_session` assinado
com HMAC (`app/core/session.py`), `HttpOnly`, `SameSite=Lax`, `Max-Age=28800`. Os
endpoints operacionais exigem esse cookie via `require_auth`; se `UI_PASSWORD` estiver
vazia, a API roda em **modo aberto** (sem auth). A assinatura usa `ARGUS_SESSION_SECRET`,
que deve ser definido explicitamente em produção. Não há armazenamento de senha em banco
nem recuperação — trocar o segredo invalida todas as sessões.

## Relatar vs ensinar

O produto final da plataforma é um **relatório de pentest/bug bounty**. Relatar
inteligência de vulnerabilidade é permitido e esperado:

- classe/classificação (CWE/OWASP), severidade (qualitativa e CVSS);
- CVE IDs e referência a exploits públicos conhecidos;
- orientação de remediação/mitigação e evidência observada (incluindo dados de scanning ativo).

Permanece proibido (em relatório e em prompts): detalhar ou ensinar técnica ofensiva,
payload, chaining ou passo-a-passo de exploração — bem como executar ataques reais fora do
Modo Diabo com os controles obrigatórios. Ver `docs/adr/0005-reporting.md`.

## Relatando vulnerabilidades

Se você encontrou uma vulnerabilidade **nesta plataforma** (não em um alvo), reporte de
forma privada:

1. Não abra issue pública.
2. Envie um relatório descrevendo: componente afetado, impacto e passos de reprodução.
3. Aguarde resposta antes de divulgar.

## Compromissos

- Tratamos relatórios de segurança com prioridade.
- Nunca commitamos segredos (`.env` está no `.gitignore`).
- Mudanças que afetem os controles de segurança passam por revisão.
