# ADR-0005 — Relatório de segurança: relatar ≠ ensinar técnica ofensiva

**Status:** Aceito

## Contexto

A plataforma foi construída com a diretriz de "não detalhar técnicas de reconhecimento,
exploração, payloads ou chaining" (Princípio 2 do ROADMAP). Ao mesmo tempo, o propósito
central do Argus Engine é ser um scanner de segurança ofensiva **autorizada** (pentest /
bug bounty), cujo entregável final é um relatório que responda: o que foi achado, por que é
uma vulnerabilidade, qual a gravidade, quais CVEs/exploits conhecidos se aplicam e como
mitigar.

Sem essa distinção, os achados ficaram genéricos ("Candidate signal for X"), a severidade
foi derivada de uma confiança artificial e o relatório passou a exibir apenas tokens/custo —
perdendo o propósito do produto.

## Decisão

- **Relatar é escopo.** O relatório de segurança pode — e deve — conter:
  - classe/classificação da vulnerabilidade (CWE / OWASP);
  - severidade real (qualitativa e/ou CVSS: score + vetor);
  - identificadores CVE aplicáveis;
  - referência a exploits públicos conhecidos (ex.: Exploit-DB, PoC publicada), sem
    descrever o mecanismo do exploit;
  - orientação de remediação/mitigação;
  - evidência observada (header, banner, versão, resposta) e referências.
- **Ensinar/executar continua proibido.** Mantém-se a proibição de detalhar técnica
  ofensiva, payload, chaining ou passo-a-passo de exploração, e de executar ataques reais
  fora do Modo Diabo (com escopo + sandbox + kill-switch + auditoria + HITL).
- **Origem dos dados.** A inteligência de vulnerabilidade (CVE/CVSS/exploit/remediação) vem
  de uma fonte determinística e curada (base de conhecimento/APIs de operador), **não** de
  texto livre gerado pelo LLM — assim o LLM resume e redige, mas não inventa CVE/severidade.
  Enquanto as ferramentas/APIs reais não existem, um "scanner simulado" gera achados de
  demonstração com a forma final correta, servindo de molde para a integração futura.

## Consequências

- System prompts dos arquétipos seguem proibindo detalhe de técnica/payload, mas passam a
  aceitar que os nós *reportem* achados estruturados (classe, CVE, severidade, remediação).
- O modelo de finding ganha campos estruturados (`category`, `affected`, `cvss_score`,
  `cvss_vector`, `cves`, `known_exploits`, `remediation`, `references`), populados pelo
  enriquecimento, não pelo LLM.
- O export/relatório é reescrito em torno desses campos; tokens/custo viram apêndice de
  observabilidade, não o conteúdo principal.
- `docs/SECURITY.md` e `docs/AGENTS.md` são atualizados para refletir a distinção
  "relatar ≠ ensinar".
