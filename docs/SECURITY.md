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

## Modo Diabo

O `DEVIL_MODE` habilita a execução real de scripts invasivos/destrutivos. Mesmo ativo,
permanecem obrigatórios: escopo validado, sandbox, kill-switch, auditoria completa e HITL.

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
