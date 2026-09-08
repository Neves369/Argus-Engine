# Guia de Cartas — Argus Engine

> Este guia explica o que cada carta faz de verdade e por que combiná-las de um
> jeito ou de outro muda o resultado. Nada aqui é decorativo: cada afirmação
> corresponde ao código real do arquétipo (`backend/app/agents/builtin.py`).

## Regra de composição

O modelo é **supervisor universal**: em todo run, quem decide quem trabalha é o
arquétipo **O Imperador**. As cartas que você coloca na mesa não definem uma
ordem de execução — elas definem **qual time o Imperador tem disponível**:

- **Mesa vazia** → o Imperador tem **todas as cartas** disponíveis para trabalhar
  (Louco, Eremita, Mago; e o Carro quando o Modo Diabo está ligado).
- **Composição montada** → o Imperador escala **apenas** as cartas escolhidas.
  Deixar uma carta fora da mesa é uma escolha: ela é **ignorada** pelo Imperador.

Por isso:

- **A ordem das cartas na mesa NÃO importa.** Elas formam um conjunto, não uma
  sequência. A posição esquerda → direita é apenas organização visual.
- **O Imperador pode repetir a mesma carta** quantas vezes julgar necessário
  (ex.: pedir mais uma rodada de coleta ao Eremita até atingir confiança),
  inclusive em composições — não existe "cada carta roda exatamente uma vez".
- **A última carta precisa continuar sendo "A Justiça"** — ela é o fechador
  fixo de todo run (valida o estado final e encerra). Você pode jogá-la junto
  com as cartas de trabalho, mas ela nunca é "delegada" como uma worker.
- Não dá pra repetir a mesma carta duas vezes na mesa (uma carta só pode ser
  liberada uma vez por sessão).
- **Clique em Finalizar Turno sem nenhuma carta na mesa** para rodar o modo
  supervisionado com o time completo do Imperador.

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
É a **carta principal de coleta**: consulta as fontes de pesquisa de verdade e
realiza **scanning ativo** do alvo. Duas camadas de coleta:

1. **Scanning ativo:** download de página, crawl de links, análise de headers
   HTTP, extração de forms/parâmetros, fingerprinting de tecnologias, detecção
   de vulnerabilidades OWASP Top 10. Roda sempre que o alvo está em
   `ALLOWED_SCOPES` (não depende do Modo Diabo). Sujeito a rate limiting,
   timeout e self-imposed restrictions (respeitar `robots.txt`).

2. **OSINT passivo:** consulta de APIs externas — NVD (CVE), crt.sh
   (certificado/subdomínio), AbuseIPDB (reputação de IP), cve.report,
   urlscan.io, ip-api.com, Shodan/InternetDB e Censys (superfície de IP),
   RDAP/whois passivo (registro de domínio) — dependendo do tipo do alvo
   (domínio vs IP; ver `docs/RUNBOOK.md` sobre chaves de API opcionais).

Todo achado que aparece no relatório final **nasce de dado observado** (fontes
ou scanning) — a coleta principal é o Eremita; o Carro (modo normal) também
sinaliza indícios a partir do mesmo material observado. Se nenhuma fonte real
tiver dado significativo pro alvo, ninguém inventa nada — o relatório fica com
zero achados, e isso é o comportamento certo, não um bug.

Achados vêm sempre marcados como **candidatos** que precisam de revisão
humana (`requires_human_review`) — o Eremita nunca confirma uma
vulnerabilidade sozinho, só levanta indícios com a evidência anexada.

**Por que jogar:** é a carta essencial. Sem ela, não existe dado real na
sessão.

### ⚔️ O Carro (`chariot`) — execução controlada / safety check

Duas caras, dependendo do **Modo Diabo**:

1. **Modo normal (Modo Diabo desligado): safety check.** O Carro observa sinais
   **não invasivos** já disponíveis — resultado do scanning ativo (headers,
   cookies, forms, fingerprint) + fontes consultadas + correlação CVE por
   banner — e **sinaliza indícios de risco** (ex.: header de segurança ausente,
   cookie sem flag, form sem proteção de CSRF, casa servidora com CVE-exploit
   público conhecido) como **achados candidatos** (`requires_human_review`).
   **Não executa nada contra o alvo** e **não pede aprovação humana**: é um
   papel passivo que adiciona lead ao relatório, sujeito à sua revisão manual.

2. **Modo Diabo ligado: execução controlada.** Cada ação destrutiva/invasiva
   **exige sua aprovação humana individual** antes de prosseguir — o run para e
   espera você aprovar ou rejeitar na tela.

**Estado atual, honestamente:** o Argus Engine **não vem com nenhum backend
de execução real** plugado nesta carta — nem por padrão, nem opcionalmente.
Mesmo aprovando a ação no Modo Diabo, a resposta é sempre um registro honesto
de que "nenhum backend de execução real está configurado" — nada é de fato
executado contra o alvo. O caminho do Modo Diabo existe hoje para
demonstrar/testar o fluxo de aprovação humana, não para realizar ações reais;
a construção de um backend de execução (testes ativos não destrutivos em modo
normal e exploits/atividades evasivas em Modo Diabo) é uma das últimas etapas
previstas no projeto.

**Por que jogar (modo normal):** para adicionar um escrutínio de riscos a partir
do que já foi observado, sem gastar nada além do que o Eremita vê.
**Por que não jogar:** se o Eremita já cobre a coleta e você não quer um agente
extra na mesa.

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

Lembrete: as cartas são um **conjunto liberado** ao Imperador, não uma ordem.
As sugestões abaixo são de *quais cartas liberar* (a Justiça sempre junto para fechar):

| Cartas na mesa | Quando usar |
|---|---|
| **Justiça sozinha (ou mesa vazia)** | Deixa o Imperador com o time completo: ele decide quem e quantas rodadas. A opção mais "automática". |
| **Eremita → Justiça** | Time restrito só à coleta: o Imperador só pode escalar o Eremita (quantas rodadas ele achar necessário). |
| **Louco → Eremita → Justiça** | Libera hipóteses + coleta: o Imperador pode alternar entre pensar e escanear. |
| **Eremita → Mago → Justiça** | Coleta + síntese para um leitor não-técnico. |
| **Carro → Justiça** (sem Eremita) | Libera apenas o safety check do Carro (modo normal): indícios de risco a partir do scan, sem coleta ampla de fontes. **Não recomendado** como única carta de coleta. |
| **Sessão completa (Louco + Eremita + Carro + Mago + Justiça)** | Todas as cartas disponíveis ao Imperador — ele monta a investigação com o deck todo. |

## O que você NÃO joga (design definido)

- **O Imperador não é uma carta.** Sob o modelo **supervisor universal**, ele
  **rege todo run** — com ou sem cartas na mesa. As cartas definem apenas o
  time que ele pode escalar:
  - mesa vazia → todas as cartas disponíveis;
  - composição → apenas as cartas escolhidas (as demais são ignoradas);
  - ele pode repetir a mesma carta e decide quando parar (a Justiça valida e
    fecha).
- O visual do Imperador permanece no `CharacterPanel` (retrato do lado aliado,
  `emperror.jpg`) como o rosto permanente da orquestração, não como carta no deck.

Se no futuro o operador quiser limitar o número de rodadas ou o orçamento do
Imperador por sessão, isso é config de supervisor, não uma carta nova.
