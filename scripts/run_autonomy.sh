#!/usr/bin/env bash
# Mantém o super agente rodando. Rode em um terminal, tmux, screen ou no cron.
# Uso: ./scripts/run_autonomy.sh [intervalo_segundos]
set -euo pipefail
INTERVALO="${1:-1800}"
cd "$(dirname "$0")/.."
exec python -m core.autonomy --loop --interval "$INTERVALO"
