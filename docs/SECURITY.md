# Política de Segurança

## Uso autorizado

O **Argus Engine** é uma plataforma de orquestração de agentes para segurança ofensiva
**autorizada**. O uso é permitido somente em:

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
| Sandbox | Execução de ferramentas isolada (Docker — Etapa 5). |
| Auditoria | Logging estruturado e histórico de decisões persistido. |
| HITL | Aprovação humana obrigatória em ações destrutivas (Modo Diabo). |
| Auth da UI | Senha única de operador + cookie de sessão assinado (HMAC, HttpOnly, SameSite=Lax). |

## Modo Diabo

O `DEVIL_MODE` habilita a execução real de scripts invasivos/destrutivos. Mesmo ativo,
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

O produto final da plataforma é um **relatório de segurança**. Relatar inteligência de
vulnerabilidade é permitido e esperado:

- classe/classificação (CWE/OWASP), severidade (qualitativa e CVSS);
- CVE IDs e referência a exploits públicos conhecidos;
- orientação de remediação/mitigação e evidência observada.

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
