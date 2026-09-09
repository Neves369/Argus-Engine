#!/usr/bin/env bash
#
# argus.sh — operação do Argus Engine via docker compose.
#
#   ops/argus.sh <modo> <comando> [opções]
#
# modos:
#   prod                  deploy de produção (Traefik + TLS + monitoring)
#   dev                   build/serviço local (compose base + monitoring dev)
#
# comandos:
#   up [--no-monitoring] [flags do docker compose]
#   down [-v]             -v remove os volumes nomeados argus-*-data
#   status
#   logs [-f] [serviço]
#   help
#
# Variáveis vêm do ambiente ou de ops/.env (default; override com
# ARGUS_OPS_ENV). Veja ops/.env.example para o template de produção.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ARGUS_OPS_ENV:-$ROOT/ops/.env}"

PROD_REQUIRED=(GHCR_OWNER TAG DOMAIN ACME_EMAIL UI_PASSWORD)
MONITORING_REQUIRED=(GRAFANA_ADMIN_PASSWORD)

log()  { printf '\033[1;36m[argus]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[argus]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[argus]\033[0m %s\n' "$*" >&2; exit 1; }

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck source=/dev/null
    . "$ENV_FILE"
    set +a
  fi
}

# Arquivos de compose relativos a $ROOT (um por linha). Caminhos relativos
# evitam quebra por espaço no diretório do repositório.
compose_files() {
  local mode="$1" monitoring="$2"
  if [[ "$mode" == dev ]]; then
    echo "docker-compose.yml"
    [[ "$monitoring" == yes ]] && echo "ops/docker-compose.monitoring.dev.yml"
    return
  fi
  echo "docker-compose.prod.yml"
  [[ "$monitoring" == yes ]] && echo "ops/docker-compose.monitoring.yml"
}

# Monta "-f <arquivo> ..." como array (paths com espaço seguros).
compose_flags() {
  local mode="$1" monitoring="$2" f
  local -a flags=()
  local file
  while IFS= read -r file; do
    flags+=(-f "$file")
  done < <(compose_files "$mode" "$monitoring")
  printf '%s\n' "${flags[@]}"
}

run_compose() {
  local mode="$1" monitoring="$2"; shift 2
  local -a flags=()
  local flag
  while IFS= read -r flag; do
    flags+=("$flag")
  done < <(compose_flags "$mode" "$monitoring")
  ( cd "$ROOT" && docker compose "${flags[@]}" "$@" )
}

# Interpolação do compose usa `:?` até em down/status/logs — exige as mesmas
# vars em qualquer comando prod.
require_prod_vars() {
  local monitoring="$1" missing=()
  local var
  for var in "${PROD_REQUIRED[@]}"; do
    [[ -n "${!var:-}" ]] || missing+=("$var")
  done
  if [[ "$monitoring" == yes ]]; then
    for var in "${MONITORING_REQUIRED[@]}"; do
      [[ -n "${!var:-}" ]] || missing+=("$var")
    done
  fi
  if ((${#missing[@]})); then
    die "variáveis obrigatórias ausentes: ${missing[*]}. Configure-as no ambiente ou em ops/.env (ver ops/.env.example)."
  fi
  if [[ -z "${ARGUS_SESSION_SECRET:-}" ]]; then
    warn "ARGUS_SESSION_SECRET vazio — recomenda-se fixar (openssl rand -hex 32) para manter sessões após rotação de senha."
  fi
}

parse_flags() {
  local mode="$1"; shift
  local monitoring=yes
  while (($#)); do
    case "$1" in
      --no-monitoring) monitoring=no ;;
      *) break ;;
    esac
    shift
  done
  echo "$monitoring|$*"
}

basename_mode() {
  local mode="$1"
  [[ "$mode" == prod ]] && echo "argus-prod" || echo "argus"
}

do_up() {
  local mode="$1" monitoring="$2"; shift 2
  if [[ "$mode" == dev ]]; then
    run_compose "$mode" "$monitoring" up -d --build "$@"
  else
    run_compose "$mode" "$monitoring" pull
    run_compose "$mode" "$monitoring" up -d "$@"
  fi
  print_urls "$mode"
}

do_down() {
  local mode="$1" monitoring="$2"; shift 2
  if [[ " $* " == *" -v "* ]]; then
    read -r -p "[argus] down -v remove os volumes argus-*-data (TSDB/Grafana/Loki). Continuar? [s/N] " answer
    [[ "${answer,,}" == "s" ]] || die "cancelado."
  fi
  run_compose "$mode" "$monitoring" down "$@"
}

do_status() {
  local mode="$1" monitoring="$2"
  run_compose "$mode" "$monitoring" ps
  echo
  if [[ "$mode" == dev ]]; then
    probe "dev UI"   "http://localhost:8080/"
    probe "prometheus" "http://localhost:9090/-/ready"
    probe "grafana"  "http://localhost:3000/api/health"
    probe "alertmanager" "http://localhost:9093/-/healthy"
  else
    probe "UI/traefik (https://$DOMAIN/)" "https://$DOMAIN/"
    if [[ "$monitoring" == yes ]]; then
      probe "grafana"      "http://localhost:3000/api/health"
      probe "alertmanager" "http://localhost:9093/-/healthy"
    fi
  fi
}

do_logs() {
  local mode="$1" monitoring="$2"; shift 2
  run_compose "$mode" "$monitoring" logs "$@"
}

probe() {
  local label="$1" url="$2"
  local code
  code=$(curl -sSo /dev/null -w '%{http_code}' --max-time 5 -k "$url" 2>/dev/null || echo 000)
  printf '  %-16s %s (HTTP %s)\n' "$label" "$url" "$code"
}

print_urls() {
  local mode="$1"
  log "stack '$(basename_mode "$mode")' no ar:"
  if [[ "$mode" == dev ]]; then
    echo "  UI          http://localhost:8080"
    echo "  Prometheus  http://localhost:9090"
    echo "  Grafana     http://localhost:3000 (admin / \$GRAFANA_ADMIN_PASSWORD)"
    echo "  Alertmanager http://localhost:9093"
  else
    echo "  UI          https://$DOMAIN"
    echo "  Grafana     http://localhost:3000 (admin / \$GRAFANA_ADMIN_PASSWORD)"
    echo "  Alertmanager http://localhost:9093"
    warn "Let's Encrypt emite o certificado na 1a requisição (porta 80 precisa estar livre):"
    echo "    curl -sI https://$DOMAIN/"
  fi
}

usage() {
  cat <<'EOF'
Uso: ops/argus.sh <modo> <comando> [opções]

modos:
  prod   deploy de produção (padrão)
  dev    serviço local com build

comandos:
  up [--no-monitoring] [flags compose]   sobe a stack
  down [-v] [flags compose]              derruba (-v remove volumes argus-*-data)
  status                                 ps + probes de saúde
  logs [-f] [serviço]                    logs (igual docker compose logs)
  help                                   este texto

variáveis (prod): GHCR_OWNER TAG DOMAIN ACME_EMAIL UI_PASSWORD
                  GRAFANA_ADMIN_PASSWORD (com monitoring) ARGUS_SESSION_SECRET (recom.)
ambiente: ARGUS_OPS_ENV=<path> para trocar o arquivo ops/.env
EOF
  exit 0
}

main() {
  local mode=prod
  if [[ "${1:-}" == prod || "${1:-}" == dev ]]; then
    mode="$1"
    shift
  fi
  local cmd="${1:-help}"
  [[ $# -gt 0 ]] && shift

  load_env

  case "$cmd" in
    help|-h|--help) usage ;;
    up)
      local parsed monitoring extra
      parsed=$(parse_flags "$mode" "$@")
      monitoring="${parsed%%|*}"
      extra="${parsed#*|}"
      if [[ "$mode" == prod ]]; then
        require_prod_vars "$monitoring"
      fi
      do_up "$mode" "$monitoring" $extra
      ;;
    down)
      local parsed monitoring extra
      parsed=$(parse_flags "$mode" "$@")
      monitoring="${parsed%%|*}"
      extra="${parsed#*|}"
      if [[ "$mode" == prod ]]; then
        require_prod_vars "$monitoring"
      fi
      do_down "$mode" "$monitoring" $extra
      ;;
    status)
      local parsed monitoring
      parsed=$(parse_flags "$mode" "$@")
      monitoring="${parsed%%|*}"
      if [[ "$mode" == prod ]]; then
        require_prod_vars "$monitoring"
      fi
      do_status "$mode" "$monitoring"
      ;;
    logs)
      local parsed monitoring extra
      parsed=$(parse_flags "$mode" "$@")
      monitoring="${parsed%%|*}"
      extra="${parsed#*|}"
      if [[ "$mode" == prod ]]; then
        require_prod_vars "$monitoring"
      fi
      do_logs "$mode" "$monitoring" $extra
      ;;
    *)
      die "comando desconhecido: $cmd (use ops/argus.sh help)"
      ;;
  esac
}

main "$@"