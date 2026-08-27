# Contributing

Obrigado pelo interesse em contribuir com o **Argus Engine**.

> **Aviso legal e ético:** este projeto só deve ser usado em alvos com autorização
> explícita e escopo definido, em conformidade com leis locais e políticas de bug bounty.
> Não são aceitas contribuições que detalhem técnicas de reconhecimento, exploração,
> payloads ou chaining de vulnerabilidades — a discussão fica no nível de arquitetura de
> software, abstração de ferramentas e fluxo de dados.

## Antes de começar

1. Leia o [ROADMAP.md](./ROADMAP.md) (plano vivo das etapas).
2. Leia o [SECURITY.md](./SECURITY.md).
3. Abra uma issue descrevendo a mudança antes de abrir um PR grande.

## Setup

### Backend (Python)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"
```

### Frontend (Vite + React)

```bash
cd frontend
npm install
```

## Convenções de código

- **Python 3.11+** (testado em 3.13), com `ruff` para lint/format.
- Formatação alinhada ao `ruff` (ver `backend/pyproject.toml`).
- Tipagem estática (`from __future__ import annotations` e anotações).
- Schemas Pydantic para entrada/saída da API.
- Nenhum segredo commitado (use `.env`, copie de `.env.example`).

## Verificações obrigatórias

```bash
cd backend
.venv\Scripts\python.exe -m ruff check app tests
.venv\Scripts\python.exe -m pytest -q
```

```bash
cd frontend
npm run lint
npm run build
```

## Fluxo de contribuição

1. Crie uma branch a partir de `main`.
2. Faça as mudanças seguindo o estilo existente.
3. Rode as verificações obrigatórias.
4. Atualize o `ROADMAP.md` se a mudança afetar o plano (marcando entregáveis).
5. Abra um PR descrevendo o que mudou e por quê.

## O que NÃO é aceito

- Técnicas ofensivas concretas (payloads, exploits, chaining) — apenas abstração e arquitetura.
- Remoção dos controles de segurança (escopo, sandbox, kill-switch, auditoria, HITL).
- Código que execute ações fora de ambiente isolado e escopo validado.
