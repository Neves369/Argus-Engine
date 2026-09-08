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
  montar a investigação. A **posição** na mesa define a ordem de execução.
- **Menu** (para abrir mais opções): **Sessões** (composições salvas),
  **Dashboard** (histórico de runs), **Modo Death / Modo Normal** (liga/desliga o
  Modo Diabo), **Configurações** e **Sair**.
- **Nova Sessão:** limpa alvo, cartas e relatório atual para começar do zero.

## 5. Os dois jeitos de rodar uma investigação

### 5.1 Sessão montada por cartas (o jeito comum na interface)

1. Defina o **alvo** (Informações do Alvo).
2. **Arraste as cartas** para a mesa, de 1 a 5, qualquer ordem — a ordem na mesa
   (esquerda → direita) **é** a ordem de execução.
3. **A última carta precisa ser A Justiça** — é ela quem fecha o run.
4. Você **não pode** repetir a mesma carta duas vezes na mesma sessão.
5. Clique em **Finalizar Turno** para executar.

Cada carta faz uma coisa específica — o resumo prático:

| Carta | Papel | Produz achado? |
|---|---|---|
| **O Louco** | Pensa em hipóteses do que investigar | Não |
| **O Eremita** | Coleta real: fontes públicas + visita o site | Sim |
| **O Mago** | Escreve um resumo "para humano" do que já foi coletado | Não |
| **A Justiça** | Fecha o run (obrigatória por último) | Avaliação final |
| **O Carro** | Ações controladas (vê seção 10 — Modo Death) | Não (hoje) |

Combinações sugeridas e o detalhe de cada carta: `docs/GUIA_CARTAS.md`.

### 5.2 Modo padrão do motor (supervisor automático, sem cartas)

Fora da montagem por cartas, o motor tem um **modo padrão**: quando um run é
iniciado **sem composição** (via API ou CLI), um supervisor — o arquétipo **O
Imperador** — decide sozinho quem vai trabalhar, em que ordem e quando parar, e
a **Justiça** fecha o run. É o comportamento automático do sistema, sem cartas na
mesa.

> Na interface hoje, o botão **Finalizar Turno** pede cartas na mesa antes de
> rodar. O modo padrão (sem cartas) é acionado quando um run é criado sem
> arquétipos — por exemplo pela API ou CLI.

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
- No canvas, o **nó ativo** fica destacado conforme o grafo avança.

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
- **Importante, honestamente:** o Argus Engine **não vem com nenhum backend de
  execução real** plugado nesta carta. Mesmo aprovando uma ação, a resposta é um
  registro honesto de que "nenhum backend de execução real está configurado" —
  **nada é de fato executado contra o alvo**. A carta existe para demonstrar e
  testar o fluxo de aprovação humana.
- Nada destrutivo acontece **sozinho**: cada ação do Modo Death para e espera
  seu **Aprovar/Rejeitar**.
- **Scanning ativo não é Modo Death.** Visitar o site, identificar tecnologias e
  detectar vulnerabilidades (de forma passiva) roda **sempre** que o alvo está em
  `ALLOWED_SCOPES`, independentemente desse toggle.

## 11. Resultados por tipo de uso — resumo

| Situação | O que acontece |
|---|---|
| **Sessão por cartas** | Segue a ordem das cartas na mesa; cada carta roda uma vez; Justiça fecha. |
| **Modo padrão (supervisor)** | O Imperador escolhe quem trabalha e quando parar; Justiça fecha. |
| **Sem chave de API** | Fontes dependentes de chave degradam para simulado → podem não gerar achados (correto). |
| **Alvo fora do escopo permitido** | Sem visita ao site e sem consultas; o sistema não trabalha lá. |
| **Modo Death ligado** | Ações controladas ficam possíveis, mas cada uma exige sua aprovação (e hoje não têm backend de execução). |
| **Interruptor de emergência** (`KILL_SWITCH`) | Interrompe o run em andamento e bloqueia novos (ação do operador — ver `RUNBOOK.md` §4). |

## 12. Problemas comuns

Para diagnósticos e incidentes (run parado, run que não inicia, senha da UI,
custo de LLM subindo, backup, falsos positivos), há um índice rápido em
`docs/RUNBOOK.md` §9. Os casos que mais aparecem:

- **"Não consigo iniciar um novo run"** — já existe um run ativo (rodando ou
  aguardando sua decisão). Termine ou decida primeiro.
- **"O run parou sem motivo"** — confira se está em `pending_review` (é decisão
  sua, não defeito) — seção 7.
- **"Relatório veio sem achados"** — pode ser o comportamento correto (sem chaves
  ou sem dado real disponível) — seções 9. Não é um bug.
- **UI pede login / senha** — consulte `RUNBOOK.md` §10.