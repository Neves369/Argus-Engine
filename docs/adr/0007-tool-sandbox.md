# ADR-0007 — Sandbox de tools via Docker CLI

**Status:** Aceito

## Contexto

Tools `kind: cli` (Etapa 5) são invocadas pelo agente via `POST /tools/{name}/invoke`
e executadas como subprocesso direto. O isolamento existente é de camada de sistema
operacional: timeout (+kill), rate limit e limites de recurso via `RLIMIT_AS`
(`TOOL_SUBPROCESS_MEMORY_LIMIT_MB`) — todos POSIX-only e dependentes da robustez do
processo pai. Para uma plataforma de pentest que executa ferramentas fornecidas pelo
operador ("tools de terceiros"), isso é um risco: um comando malicioso ou com bug
roda com os mesmos privilégios do serviço, com acesso à rede do host e a qualquer
arquivo legível pelo usuário do processo.

Precisa-se de isolamento no nível de container para tools CLI, sem:
- introduzir dependência nova no backend (SDK/daemon HTTP do Docker);
- mudar o contrato da API já existente;
- quebrar o comportamento default atual (opt-in);

e com garantia de **fail-closed**: quando o operador pede sandbox e o ambiente Docker
não está disponível, a tool **não deve rodar** — nunca cair em silêncio para o
caminho sem isolamento.

## Decisão

- **`docker` CLI via subprocess** (exec form, sem shell), em `app/tools/executor.py::_execute_cli_sandbox`. Nenhuma dependência nova (não usamos SDK `docker` Python nem `docker-py`).
- Invocação: `docker run --rm --name argus-sandbox-<uuid>` com hardening por padrão:
  - rede `--network=none` (override por tool via `ToolSpec.sandbox_network`);
  - root filesystem `--read-only` + `--tmpfs /tmp:rw,size=64m`;
  - `--cap-drop ALL`, `--security-opt no-new-privileges`;
  - `--pids-limit`, `--cpus`, `--memory`/`--memory-swap` (memória reusa `tool_subprocess_memory_limit_mb`), `--ulimit nofile=256:256`;
  - usuário não-root (`TOOL_SANDBOX_UID`, default 65534; override por tool via `ToolSpec.sandbox_user`);
  - `--stop-timeout` igual ao timeout da tool.
- Config opt-in: `TOOL_SANDBOX` (default `false`). Imagem default `TOOL_SANDBOX_IMAGE=alpine:latest`; por tool, `ToolSpec.sandbox_image`.
- **Fail-closed:** `shutil.which("docker")` ausente → sobe `ToolExecutionError` ("docker binary not found (TOOL_SANDBOX is enabled)"); returncode 125 do docker (falha do daemon) → `ToolExecutionError` com o stderr truncado. Nunca fallback para subprocesso.
- Timeout: `wait_for` no `communicate`; em estouro, `process.kill()` + `docker rm -f <name>` (best-effort) para não deixar container órfão.
- Testes: unit determinísticos com mock de `asyncio.create_subprocess_exec` (argv, fail-closed, override por tool, timeout/cleanup, truncation) + integração real com `alpine`+`echo` gated por `ARGUS_TEST_SANDBOX=1`.
- Fora do escopo desta esta decisão: credenciais/volumes para dentro do container (sobe em ADR futuro se houver necessidade); tools `kind: http` (não passam pelo executor CLI).

## Consequências

- O `ToolSpec` ganha campos opcionais `sandbox_image`, `sandbox_network`, `sandbox_user`.
- `docs/SECURITY.md`, `docs/RUNBOOK.md` (§6.7), `docs/ROADMAP.md` (Etapa 5) e `backend/.env.example` foram atualizados para refletir a decisão e as varáveis.
- Operacional: primeira execução por imagem faz pull dentro do timeout da tool — recomendação é pré-puxar (`docker pull`); ver ROADMAP Etapa 5 e RUNBOOK §6.7.
- O host precisa de Docker acessível ao usuário do serviço; indisponibilidade == tool indisponível (fail-closed, por design).