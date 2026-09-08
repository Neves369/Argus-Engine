# Manual do Usuário — Argus Engine

> Este manual é para quem **usa** a plataforma: operador de segurança autorizado
> que roda investigações contra alvos declarados. Para quem **opera/sobe** o
> serviço (configuração, incidentes, backup), ver `docs/RUNBOOK.md`. Para o
> detalhe de cada carta, ver `docs/GUIA_CARTAS.md`.

## 1. O que é

O Argus Engine é uma plataforma de **pentest e bug bounty autorizado**. Você
define um alvo, escolhe como um time de "papeis" vai trabalhar nele, e o sistema
**investiga o alvo de verdade** — consultando bases públicas de segurança,
visitando o site (se permitido) e cruzando o que encontrou com vulnerabilidades
conhecidas. No final você recebe um **relatório** com os achados, evidências e
recomendações.

Duas regras valem para tudo:

- **Uso autorizado apenas.** O sistema só toca em alvos que você declarou na
  lista de permitidos (`ALLOWED_SCOPES`). Fora dela, nada é feito.
- **Nada é inventado.** Todo achado do relatório nasce de um dado real (fonte
  pública ou exame do site) e chega marcado como **candidato** — cabe a você
  validar antes de agir. Se não há dado confiável, o relatório fica sem achado:
  isso é comportamento correto, não um defeito.

## 2. Antes de começar

- [ ] O serviço está no ar (ver `docs/RUNBOOK.md` §2 para subir).
- [ ] O alvo que você vai investigar está na lista de permitidos do ambiente
  (`ALLOWED_SCOPES`). Sem isso o sistema não coloca a mão no alvo.
- [ ] (Opcional) As chaves de API desejadas estão preenchidas no `.env`
  (ver seção 9 — o que muda nos resultados).

## 3. Como acessar

- **Web (interface visual):** abra o endereço do serviço no navegador. Se uma
  senha foi configurada (`UI_PASSWORD`), aparece a tela de login com essa senha;
  se não, a interface entra direto (modo aberto — só para ambiente de teste).
- **Linha de comando (CLI):** rode `argus --help` para ver os comandos
  disponíveis (montar sessão, executar, revisar, exportar, testar fontes,
  rodar ferramentas).

## 4. A tela principal

- **Alvo:** o botão que abre *Informações do Alvo* deixa você preencher o **Nome**
  (domínio ou IP), a **URL** (se quiser) e **Informações Adicionais**.
- **A mesa de cartas:** no centro, você arrasta as cartas (os "papeis") para
  montar a investigação. A **posição na mesa não define ordem de execução** —
  as cartas formam o conjunto de agentes que o Imperador pode usar.
- **Menu** (para abrir mais opções): **Sessões** (composições salvas),
  **Dashboard** (histórico de runs), **Modo Death / Modo Normal** (liga/desliga o
  Modo Diabo), **Configurações** e **Sair**.
- **Nova Sessão:** limpa alvo, cartas e relatório atual para começar do zero.

## 5. Como rodar uma investigação

O Argus Engine usa um **supervisor universal**: quem decide quem trabalha em um
run é o arquétipo **O Imperador**. As cartas que você coloca na mesa definem
**o time que o Imperador pode escalar** — nada além disso.

### 5.1 Mesa vazia — o Imperador decide tudo

1. Defina o **alvo** (Informações do Alvo).
2. **Não jogue nenhuma carta.**
3. Clique em **Finalizar Turno**.

O Imperador usa o **time completo** (Louco, Eremita, Mago — e o Carro com o
Modo Death ligado), decide quem roda a cada rodada, pode **repetir** a mesma
carta se achar necessário e fecha quando a investigação estiver suficiente
(a Justiça valida e encerra).

### 5.2 Sessão montada por cartas — você limita o time

1. Defina o **alvo** (Informações do Alvo).
2. **Jogue as cartas** que quer liberar (de 1 a 5; sem repetir a mesma carta).
3. **A última carta precisa ser A Justiça** — ela fecha o run.
4. Clique em **Finalizar Turno**.

Aqui o Imperador escala **apenas** as cartas escolhidas; as que você deixou de
fora da mesa são ignoradas. **A ordem das cartas na mesa não importa** — é só o
conjunto disponível que vale.

Cada carta faz uma coisa específica — o resumo prático:

| Carta | Papel | Produz achado? |
|---|---|---|
| **O Louco** | Pensa em hipóteses do que investigar | Não |
| **O Eremita** | Coleta real: fontes públicas + visita o site | Sim |
| **O Mago** | Escreve um resumo "para humano" do que já foi coletado | Não |
| **A Justiça** | Fecha o run (obrigatória por último) | Avaliação final |
| **O Carro** | Safety check no modo normal (indícios de risco); execução controlada no Modo Death (vê seção 10) | Sim (indícios candidatos) |

Combinações sugeridas e o detalhe de cada carta: `docs/GUIA_CARTAS.md`.

## 6. Rodando e acompanhando ao vivo

- **Finalizar Turno** inicia o run. Só pode haver **um run ativo por vez** — se já
  houver um rodando ou aguardando decisão sua, o início será recusado até ele
  terminar.
- Enquanto roda, o painel mostra o andamento em **tempo real**:
  - **Resultados** (abre sozinha ao concluir): os achados aparecem com severidade,
    CVEs, referências, remediação e evidência. Muitos achados já entram **ao vivo**
    durante a execução, não só no fim.
  - **Log**: a trilha de passos do run.
  - **Chat**: as mensagens trocadas pelos agentes.
- No modo normal (sem Modo Death), o **Carro** roda uma camada de **execução real
  não destrutiva**: ele **verifica ao vivo** cada lead do scan contra o alvo
  (uma consulta simples, respeitando scope/robots) e também pode invocar **uma
  vez cada ferramenta de checagem** que o operador do sistema tiver registrado
  (ex.: um verificador de status HTTP). Nada disso toca em exploits nem em
  atividade evasiva — é checagem, não ataque.
- No canvas, o **nó ativo** fica destacado conforme o grafo avança.
- **Se o run for cancelado (ou falhar) no meio**, o sistema guarda o estado até
  aquele momento. Ao abrir esse run (Dashboard/Sessões → **Ver**), o painel mostra
  **Retomar run de onde parou**: a investigação continua a partir da última etapa
  executada — histórico, log e chat já ficam pré-carregados e só recebem as
  entradas novas — sem recomeçar do zero.

## 7. Quando o sistema pede a sua aprovação

Em certas situações o run **para** e espera uma decisão humana:

- **Ações do Modo Death** (destrutivas) — cada ação precisa do seu **Aprovar /
  Rejeitar** individualmente.
- Achados que o sistema sinaliza como incertos.

Na tela, o painel mostra a **revisão** (o contexto + a proposta resumida) com
botões **Aprovar** e **Rejeitar**. Pela linha de comando:

```bash
argus compose pending              # lista runs aguardando sua decisão
argus compose review <RUN_ID> --approve   # ou: --reject
```

**Regra:** nunca aprove sem ler o contexto/proposta — é exatamente o resumo
montado para essa decisão. Um run parado em `pending_review` mantém o lock
(continua sendo o único ativo) até você decidir.

## 8. Lendo o relatório e exportando

Depois que o run conclui, o painel cai na aba **Resultados**. Cada achado traz:

- **Severidade**: critical / high / medium / low / info
- **Categoria** (padrões como CWE/OWASP) e, quando aplicável, **escore CVSS**
- **CVEs** relacionados e referência a **exploit público conhecido**, se houver
- **Verificação ao vivo** (quando o Carro sondou o lead em modo normal), em três
  estados:
  - **verificado ao vivo** — o lead continua presente na resposta fresca do alvo;
  - **não reprovado** — a resposta fresca não reproduziu o lead (por exemplo, o
    header de segurança passou a existir);
  - **verificação pulada** — a sonda não pôde ser enviada (fora de escopo, alvo
    fora do ar ou bloqueado por `robots.txt`); o motivo aparece junto ao selo.
- **Remediação**: o que fazer para corrigir
- **Evidência**: o dado real que sustentou o achado
- **Referências** para consulta

O relatório também pode ser **exportado** em Markdown, JSON, CSV, SARIF ou PDF
(botão **Exportar** no painel). Pela API, o relatório estruturado fica em
`GET /runs/{id}/report` e o export em `GET /runs/{id}/export`.

Para **runs antigos**, abra o **Dashboard** (coluna *Ações*: **Ver** para abrir
somente-leitura, ou **Revisar** quando aguarda decisão) ou a aba **Sessões**.

## 9. Chaves de API — o que muda nos resultados

O sistema consulta bases públicas sem precisar de chave na maioria delas. Algumas
fontes ficam melhores (ou só funcionam de verdade) com chave. Sem a chave, a
fonte **degrada para simulado** e **não gera achado** — nunca inventa dado.

| Contexto | Fontes | Com chave | Sem chave |
|---|---|---|---|
| **Domínio** | NVD (CVEs), crt.sh (subdomínios), HackerTarget (DNS), RDAP (registro do domínio) | NVD mais generoso | Tudo funciona; NVD com cota menor |
| **Domínio** | urlscan.io (avaliações públicas) | Cota maior | Funciona com cota anônima |
| **IP** | InternetDB, ip-api (geolocalização) | — | Funcionam sempre |
| **IP** | Shodan (`SHODAN_API_KEY`), Censys (`CENSYS_API_TOKEN`) | Dados reais (portas/CVEs/serviços) | Degradam para simulado (sem achado) |
| **Qualquer** | AbuseIPDB (`ABUSEIPDB_API_KEY`) | Reputação real de IP | Todos os checks falham → simulado |

As chaves ficam no arquivo de ambiente (`.env`) do operador — consulte
`docs/RUNBOOK.md` §3 e `backend/.env.example`.

## 10. Modo Death / Modo Diabo — o que ele é hoje

- O toggle **Modo Death** no menu habilita o modo de execução destrutiva/invasiva
  (o arquétipo **O Carro**).
- **Sem o Modo Death**, o Carro roda o **modo normal**: observa sinais não
  invasivos já disponíveis (scan passivo, fontes, correlação CVE) e sinaliza
  **indícios de risco** como achados candidatos — e em seguida **verifica-os ao
  vivo** contra o alvo (checagem, não ataque) e roda as ferramentas de checagem
  do operador, tudo respeitando escopo/robots e sem exigir aprovação.
- **Com o Modo Death**, cada ação do Carro para e espera seu **Aprovar /
  Rejeitar** individual.
- **Importante, honestamente:** no **Modo Death** não há backend de execução
  destrutiva. Mesmo aprovando uma ação, a resposta é um registro honesto de que
  "nenhum backend de execução real está configurado" — **nada destrutivo é de
  fato executado contra o alvo**. O Modo Death existe para demonstrar e testar o
  fluxo de aprovação humana (as sondas e ferramentas de checagem não destrutivas
  do modo normal são a execução real que já existe — ver `docs/adr/0009-chariot-execution.md`).
- Nada destrutivo acontece **sozinho**: cada ação do Modo Death para e espera
  seu **Aprovar/Rejeitar**.
- **Scanning ativo não é Modo Death.** Visitar o site, identificar tecnologias e
  detectar vulnerabilidades (de forma passiva) roda **sempre** que o alvo está em
  `ALLOWED_SCOPES`, independentemente desse toggle.

## 11. Resultados por tipo de uso — resumo

| Situação | O que acontece |
|---|---|
| **Mesa vazia** | O Imperador usa o time completo (Louco, Eremita, Mago, +Carro no Death), decide quem roda e quando parar; Justiça fecha. |
| **Sessão por cartas** | O Imperador escala apenas as cartas escolhidas (ordem na mesa não importa); Justiça fecha. |
| **Sem chave de API** | Fontes dependentes de chave degradam para simulado → podem não gerar achados (correto). |
| **Alvo fora do escopo permitido** | Sem visita ao site e sem consultas; o sistema não trabalha lá. |
| **Modo normal** | O Carro verifica ao vivo os leads do scan e roda as ferramentas de checagem do operador (não destrutivas), sem exigir aprovação. |
| **Modo Death ligado** | O Carro vira execução controlada; cada ação exige sua aprovação (no Death, sem backend de execução destrutiva por enquanto). |
| **Interruptor de emergência** (`KILL_SWITCH`) | Interrompe o run em andamento e bloqueia novos (ação do operador — ver `RUNBOOK.md` §4). |

## 12. Problemas comuns

Para diagnósticos e incidentes (run parado, run que não inicia, senha da UI,
custo de LLM subindo, backup, falsos positivos), há um índice rápido em
`docs/RUNBOOK.md` §9. Os casos que mais aparecem:

- **"Não consigo iniciar um novo run"** — já existe um run ativo (rodando ou
  aguardando sua decisão). Termine ou decida primeiro.
- **"O run parou sem motivo"** — confira se está em `pending_review` (é decisão
  sua, não defeito) — seção 7.
- **"O run cancelou/falhou no meio"** — não precisa refazer do zero: abra o run e
  use **Retomar run de onde parou** (seção 6).
- **"Relatório veio sem achados"** — pode ser o comportamento correto (sem chaves
  ou sem dado real disponível) — seções 9. Não é um bug.
- **UI pede login / senha** — consulte `RUNBOOK.md` §10.