#!/usr/bin/env bash
# Runs inside Oracle Linux 9 (or any host with RUN_ON_HOST_OL9=1).
# Full integration: compose up -> health -> ingest -> RAG -> host pytest.
set -euo pipefail

ROOT="${ROOT:-/work}"
cd "${ROOT}"

COMPOSE_PROJECT="${COMPOSE_PROJECT:-ol9-integration-test}"
API_CONTAINER="${API_CONTAINER:-fastapi-llm-rag-cookbook-api}"
CHROMA_CONTAINER="${CHROMA_CONTAINER:-fastapi-llm-rag-cookbook-chroma}"
LOG_DIR="${LOG_DIR:-${ROOT}/logs}"
KEEP_STACK="${KEEP_STACK:-0}"
SKIP_COMPOSE_UP="${SKIP_COMPOSE_UP:-0}"
API_WAIT_SECS="${API_WAIT_SECS:-900}"
API_POLL_SECS="${API_POLL_SECS:-15}"

mkdir -p "${LOG_DIR}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR}/ol9_integration_${TS}.log"

tlog() {
  echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${LOG_FILE}"
}

fail() {
  tlog "FAIL: $*"
  if [[ "${KEEP_STACK}" != "1" ]]; then
    tlog "tearing down compose project ${COMPOSE_PROJECT}"
    docker compose -p "${COMPOSE_PROJECT}" -f docker-compose.yml down >>"${LOG_FILE}" 2>&1 || true
  fi
  exit 1
}

dc() {
  docker compose -p "${COMPOSE_PROJECT}" -f docker-compose.yml "$@"
}

dc_ingest() {
  docker compose -p "${COMPOSE_PROJECT}" \
    -f docker-compose.yml \
    -f docker-compose.ingest.yml \
    "$@"
}

api_curl() {
  docker exec "${API_CONTAINER}" curl -sf "$@"
}

health_json() {
  api_curl http://127.0.0.1:8000/health
}

assert_health_ok() {
  local body="$1"
  echo "${body}" | grep -q '"status":"ok"' || fail "health status not ok"
  echo "${body}" | grep -q '"chroma_mode":"http"' || fail "expected chroma_mode http"
}

assert_min_chunks() {
  local body="$1"
  local min="$2"
  echo "${body}" | python3 -c "
import json, sys
min_chunks = int(sys.argv[1])
data = json.load(sys.stdin)
chunks = int(data.get('indexed_chunks', -1))
if chunks < min_chunks:
    raise SystemExit(f'indexed_chunks={chunks} < {min_chunks}')
" "${min}" || fail "indexed_chunks check failed"
}

wait_for_api() {
  tlog "waiting for ${API_CONTAINER}, max ${API_WAIT_SECS}s"
  local elapsed=0
  while (( elapsed < API_WAIT_SECS )); do
    if health_json >/tmp/ol9-health.json 2>/dev/null; then
      tlog "api ready: $(tr -d '\n' </tmp/ol9-health.json)"
      return 0
    fi
    sleep "${API_POLL_SECS}"
    elapsed=$((elapsed + API_POLL_SECS))
    tlog "still waiting ${elapsed}s"
  done
  fail "api not ready after ${API_WAIT_SECS}s"
}

tlog "=== OL9 integration test project=${COMPOSE_PROJECT} ==="
tlog "log file: ${LOG_FILE}"
tlog "os: $(head -1 /etc/os-release 2>/dev/null || uname -a)"

command -v docker >/dev/null || fail "docker not in PATH"
command -v python3 >/dev/null || dnf install -y python3 >>"${LOG_FILE}" 2>&1

if [[ "${SKIP_COMPOSE_UP}" != "1" ]]; then
  tlog "stopping previous cookbook stacks"
  for proj in "${COMPOSE_PROJECT}" ol9test cookbook-verify work; do
    docker compose -p "${proj}" -f docker-compose.yml down >>"${LOG_FILE}" 2>&1 || true
  done
  docker rm -f "${API_CONTAINER}" "${CHROMA_CONTAINER}" >>"${LOG_FILE}" 2>&1 || true

  tlog "docker compose up --build -d"
  dc up --build -d 2>&1 | tee -a "${LOG_FILE}"
else
  tlog "SKIP_COMPOSE_UP=1, using existing containers"
fi

tlog "chroma: $(docker inspect -f '{{.State.Health.Status}}' "${CHROMA_CONTAINER}" 2>/dev/null || echo unknown)"
wait_for_api

tlog "test: health before ingest"
body="$(health_json)"
assert_health_ok "${body}"
tlog "pre-ingest health ok"

tlog "test: ingest"
dc_ingest run --rm ingest 2>&1 | tee -a "${LOG_FILE}"

tlog "test: health after ingest"
body="$(health_json)"
assert_health_ok "${body}"
assert_min_chunks "${body}" 1

tlog "test: RAG ask"
rag="$(api_curl -X POST http://127.0.0.1:8000/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What is ChromaDB used for?"}')"
tlog "rag response: ${rag}"
echo "${rag}" | grep -q '"answer"' || fail "rag missing answer"
echo "${rag}" | grep -q '"sources"' || fail "rag missing sources"

tlog "test: host pytest on OL9 python3"
tlog "system sqlite: $(python3 -c 'import sqlite3; print(sqlite3.sqlite_version)')"

if ! command -v uv >/dev/null; then
  tlog "installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh >>"${LOG_FILE}" 2>&1
  export PATH="${HOME}/.local/bin:${PATH}"
fi

dnf install -y tar gzip which >>"${LOG_FILE}" 2>&1 || true
uv sync 2>&1 | tee -a "${LOG_FILE}"
uv run --python python3 ruff check . 2>&1 | tee -a "${LOG_FILE}"
uv run --python python3 pytest -v 2>&1 | tee -a "${LOG_FILE}"

if [[ "${KEEP_STACK}" != "1" ]]; then
  tlog "tearing down compose project ${COMPOSE_PROJECT}"
  dc down >>"${LOG_FILE}" 2>&1
fi

tlog "=== ALL TESTS PASSED ==="
SUMMARY="${LOG_DIR}/ol9_integration_${TS}_summary.txt"
cat >"${SUMMARY}" <<EOF
ol9_integration_test: PASSED
timestamp_utc: ${TS}
compose_project: ${COMPOSE_PROJECT}
log: ${LOG_FILE}
EOF
tlog "summary: ${SUMMARY}"
