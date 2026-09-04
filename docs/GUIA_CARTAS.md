# Guia de Cartas — Argus Engine

> Este guia explica o que cada carta faz de verdade e por que combiná-las de um
> jeito ou de outro muda o resultado. Nada aqui é decorativo: cada afirmação
> corresponde ao código real do arquétipo (`backend/app/agents/builtin.py`).

## Regra de composição

- Uma sessão pode ter de 1 a 5 cartas na mesa, em qualquer ordem da esquerda
  pra direita — essa ordem **é** a ordem de execução.
- **A última carta jogada precisa ser "A Justiça"** — é ela quem fecha o run.
  Sem isso, o botão de executar retorna erro.
- Não dá pra repetir a mesma carta duas vezes na mesma sessão.
- Diferente do "modo padrão" do motor (usado internamente, sem cartas), uma
  composição feita com cartas roda **cada carta exatamente uma vez**, na
  ordem escolhida — não existe repetição automática do Eremita até atingir
  confiança alta. Se você quer mais uma rodada de coleta, jogue a carta do
  Eremita de novo numa próxima sessão, depois de revisar o que já veio.

## As cartas, uma por uma

### 🃏 O Louco (`fool`) — hipóteses
Levanta hipóteses do que vale investigar, usando só o que **já** foi
observado por outras cartas jogadas antes dela (ou, se jogada primeiro,
raciocina só sobre o nome do alvo). **Não consulta nenhuma fonte real** —
é puramente um passo de raciocínio (LLM). Não produz achado nenhum sozinho.

**Por que jogar:** quando você quer que o sistema pense em voz alta sobre
por onde começar, antes de gastar chamadas reais de API em fontes externas.

**Por que não jogar:** se você já sabe exatamente o que quer verificar — vá
direto ao Eremita.

### 🔍 O Eremita (`hermit`) — coleta real
É a **única carta que consulta as fontes de pesquisa de verdade** e realiza
**scanning ativo** do alvo. Duas camadas de coleta:

1. **Scanning ativo:** download de página, crawl de links, análise de headers
   HTTP, extração de forms/parâmetros, fingerprinting de tecnologias, detecção
   de vulnerabilidades OWASP Top 10. Roda sempre que o alvo está em
   `ALLOWED_SCOPES` (não depende do Modo Diabo). Sujeito a rate limiting,
   timeout e self-imposed restrictions (respeitar `robots.txt`).

2. **OSINT passivo:** consulta de APIs externas — NVD (CVE), crt.sh
   (certificado/subdomínio), AbuseIPDB (reputação de IP), cve.report,
   urlscan.io e ip-api.com — dependendo do tipo do alvo (domínio vs IP; ver
   `docs/RUNBOOK.md` sobre chaves de API opcionais).

Todo achado que aparece no relatório final **nasce aqui** (ou não aparece).
Se nenhuma fonte real tiver dado significativo pro alvo, o Eremita não
inventa nada — o relatório fica com zero achados, e isso é o comportamento
certo, não um bug.

Achados vêm sempre marcados como **candidatos** que precisam de revisão
humana (`requires_human_review`) — o Eremita nunca confirma uma
vulnerabilidade sozinho, só levanta indícios com a evidência anexada.

**Por que jogar:** é a carta essencial. Sem ela, não existe dado real na
sessão.

### ⚔️ O Carro (`chariot`) — execução controlada
Só faz alguma coisa quando o **Modo Diabo** está ligado (o toggle de morte
no topo da tela). Quando ligado, qualquer ação dessa carta **exige
aprovação humana explícita** antes de prosseguir — o run para e espera você
aprovar ou rejeitar na tela.

**Estado atual, honestamente:** o Argus Engine **não vem com nenhum backend
de execução real** plugado nesta carta — nem por padrão, nem opcionalmente.
Mesmo aprovando a ação, a resposta é sempre um registro honesto de que
"nenhum backend de execução real está configurado" — nada é de fato
executado contra o alvo. A carta existe hoje para demonstrar/testar o fluxo
de aprovação humana (human-in-the-loop), não para realizar ações reais.

**Por que jogar:** só se você quer ver/testar o fluxo de aprovação em ação.
**Por que não jogar:** se seu objetivo é reconhecimento de verdade — ela não
adiciona achado nenhum ao relatório hoje.

### 🌀 O Mago (`magician`) — síntese
Não consulta nada novo. Pega tudo que **já foi acumulado** até aquele ponto
da sessão (achados, evidências, fontes consultadas) e escreve um resumo em
linguagem natural do estado atual da investigação.

**Por que jogar:** quando você vai levar o resultado pra alguém que não vai
ler o relatório técnico bruto — o resumo do Mago é a versão "para humano".
**Por que não jogar antes do Eremita:** se jogada antes de qualquer coleta,
não tem o que sintetizar — o resumo sai vazio.

### ⚖️ A Justiça (`justice`) — fechamento (obrigatória)
Sempre a última carta. Revisa o que foi acumulado e escreve uma avaliação
final de auditoria — não decide sozinha se um achado é válido ou não (isso é
o pipeline de qualidade + sua revisão manual via `/findings/{id}/validate`),
só resume o estado final pro registro.

## Combinações recomendadas

| Combinação | Quando usar |
|---|---|
| **Eremita → Justiça** | O mínimo útil. Scanning ativo + OSINT passivo + fechamento. Use quando já sabe o alvo e quer um scan completo. |
| **Louco → Eremita → Justiça** | Quando quer que o sistema pense no que procurar antes de escanear e consultar as fontes. |
| **Eremita → Mago → Justiça** | Quando o resultado vai para alguém não-técnico — adiciona um resumo em linguagem natural. |
| **Louco → Eremita → Mago → Justiça** | A sessão "completa": hipótese → scanning ativo + coleta real → síntese → fechamento. |
| **Carro → Justiça** (sem Eremita) | **Não recomendado.** Sem scanning ativo antes, não há nada para basear uma ação, e não há backend real por trás mesmo assim — a sessão fecha sem achado nenhum. |
| **Justiça sozinha** | Válido pelas regras, mas inútil — fecha uma sessão vazia, sem nenhum scan. |

## O que NÃO está nas cartas (ainda)

O arquétipo "O Imperador" (planejador/diretor) existe no motor mas **não é
uma carta jogável** na interface atual — ele só participa do modo padrão
interno do sistema, não das sessões montadas por você. Se isso mudar, este
guia será atualizado.
