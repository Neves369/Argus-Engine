# Política de Uso Autorizado — Argus Engine

**Versão:** 1.0.0

## 1. Princípio

O Argus Engine é uma plataforma de orquestração de agentes para segurança ofensiva
**autorizada**. Seu uso é estritamente limitado a atividades com autorização explícita.

## 2. Requisitos para uso

Antes de iniciar qualquer run, o operador deve confirmar que:

1. Possui autorização explícita do dono do ativo.
2. O alvo está dentro do escopo definido e documentado.
3. A atividade está em conformidade com as leis locais aplicáveis.
4. Em programas de bug bounty, o programa autoriza explicitamente os testes realizados.

## 3. Escopo

- O escopo é definido via `ALLOWED_SCOPES` e validado em tempo de execução por `validate_scope`.
- Qualquer alvo fora do escopo é recusado automaticamente.

## 4. Controles obrigatórios

- Sandbox para execução de ferramentas.
- Kill-switch disponível a qualquer momento.
- Auditoria completa (logging estruturado + histórico de decisões).
- HITL (aprovação humana) em ações destrutivas.

## 5. Modo Diabo

O Modo Diabo (execução real de scripts invasivos/destrutivos) só pode ser ativado com
escopo validado, sandbox, kill-switch, auditoria completa e HITL em ações destrutivas.

## 6. Proibições

- Uso em alvos sem autorização explícita.
- Uso para fins ilegais ou fora do escopo autorizado.
- Detalhamento ou compartilhamento de técnicas ofensivas concretas.

## 7. Responsabilidade

O operador é o único responsável pelo uso adequado e pela autorização. O uso indevido
viola esta política e os termos da licença.
