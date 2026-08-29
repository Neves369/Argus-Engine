#!/usr/bin/env bash
# Sobe backend (uvicorn) e frontend (Vite) ao mesmo tempo.
# Ctrl+C encerra os dois processos.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve o binário do uvicorn: prefere o venv do backend, senão o PATH.
UVICORN_BIN="$ROOT/backend/.venv/bin/uvicorn"
if [ ! -x "$UVICORN_BIN" ]; then
  UVICORN_BIN="$(command -v uvicorn || true)"
fi

if [ -z "$UVICORN_BIN" ]; then
  echo "uvicorn não encontrado. Configure o backend primeiro:"
  echo "  cd backend && make setup"
  exit 1
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "Encerrando backend e frontend..."
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "Iniciando backend em http://localhost:8000 ..."
(
  cd "$ROOT/backend"
  "$UVICORN_BIN" app.main:app --reload --port 8000
) &
BACKEND_PID=$!

# Só sobe o frontend depois que o backend terminar o startup (migrações Alembic
# rodam no lifespan; /health só responde após tudo pronto). Evita os erros de
# proxy ("ECONNREFUSED") do Vite enquanto o backend ainda não escuta na 8000.
echo "Aguardando backend responder em http://localhost:8000 ..."
backend_ready=false
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    backend_ready=true
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    break
  fi
  sleep 0.5
done

if [ "$backend_ready" = false ]; then
  echo "Backend não respondeu em http://localhost:8000/health. Veja os logs acima e ajuste .env/banco se necessário."
  exit 1
fi

echo "Iniciando frontend (Vite) em http://localhost:5173 ..."
(
  cd "$ROOT/frontend"
  npm run dev
) &
FRONTEND_PID=$!

echo ""
echo "Pronto! Acesse o frontend em http://localhost:5173 (proxy /api -> :8000)"
echo "Pressione Ctrl+C para encerrar os dois."

wait
