#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="${DSA_COMPOSE_FILE:-$REPO_ROOT/docker/docker-compose.yml}"
LOCK_DIR="${DSA_ANALYSIS_LOCK_DIR:-$REPO_ROOT/data/.scheduled-analysis.lock}"

mkdir -p "$(dirname -- "$LOCK_DIR")"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "scheduled analysis is already running; lock exists: $LOCK_DIR" >&2
    exit 75
fi

cleanup() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if docker compose version >/dev/null 2>&1; then
    compose() {
        docker compose "$@"
    }
elif command -v docker-compose >/dev/null 2>&1; then
    compose() {
        docker-compose "$@"
    }
else
    echo "docker compose or docker-compose is required" >&2
    exit 127
fi

cd "$REPO_ROOT"
compose -f "$COMPOSE_FILE" --profile scheduler run --rm --no-deps \
    -e SCHEDULE_ENABLED=false \
    -e SCHEDULE_RUN_IMMEDIATELY=false \
    -e RUN_IMMEDIATELY=true \
    analyzer python main.py
