#!/usr/bin/env bash
# Systematic retest of README.md workflows. Logs all output to logs/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG_DIR="${ROOT}/logs"
mkdir -p "$LOG_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${LOG_DIR}/readme_retest_${TS}.log"
SUMMARY_FILE="${LOG_DIR}/readme_retest_${TS}_summary.txt"

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
CURL_OPTS=(--connect-timeout 5 --max-time 120 -sS)
SERVER_PID=""
STARTED_SERVER=0
PASS=0
FAIL=0
SKIP=0

log() {
  local msg="$1"
  echo "$msg" | tee -a "$LOG_FILE"
}

section() {
  log ""
  log "================================================================================"
  log "SECTION: $1"
  log "================================================================================"
}

run_step() {
  local id="$1"
  local desc="$2"
  shift 2
  log ""
  log "--- [$id] $desc ---"
  log "CMD: $*"
  local start end rc
  start=$(date +%s)
  set +e
  {
    echo "EXIT: pending"
    "$@"
  } >>"$LOG_FILE" 2>&1
  rc=$?
  set -e
  end=$(date +%s)
  if [[ $rc -eq 0 ]]; then
    log "RESULT: PASS (exit 0, ${start}s-${end}s)"
    PASS=$((PASS + 1))
    echo "PASS  $id  $desc" >>"$SUMMARY_FILE"
  else
    log "RESULT: FAIL (exit $rc, ${start}s-${end}s)"
    FAIL=$((FAIL + 1))
    echo "FAIL  $id  $desc  exit=$rc" >>"$SUMMARY_FILE"
  fi
  return 0
}

skip_step() {
  local id="$1"
  local desc="$2"
  local reason="$3"
  log ""
  log "--- [$id] $desc ---"
  log "RESULT: SKIP ($reason)"
  SKIP=$((SKIP + 1))
  echo "SKIP  $id  $desc  $reason" >>"$SUMMARY_FILE"
}

wait_for_health() {
  local url="$1"
  local max_wait="${2:-180}"
  local i=0
  while (( i < max_wait )); do
    if curl "${CURL_OPTS[@]}" "$url/health" >/dev/null 2>&1; then
      log "Server ready at $url (${i}s)"
      return 0
    fi
    sleep 2
    i=$((i + 2))
  done
  log "Server not ready at $url after ${max_wait}s"
  return 1
}

start_server_if_needed() {
  if curl "${CURL_OPTS[@]}" "$BASE_URL/health" >/dev/null 2>&1; then
    log "Using existing server at $BASE_URL"
    return 0
  fi
  log "Starting server in background..."
  unset CHROMA_HOST
  export CHROMA_HOST=
  uv run python -m uvicorn main:app --host 127.0.0.1 --port 8000 >>"$LOG_FILE" 2>&1 &
  SERVER_PID=$!
  STARTED_SERVER=1
  if ! wait_for_health "$BASE_URL" 600; then
    return 1
  fi
}

cleanup() {
  if [[ "$STARTED_SERVER" -eq 1 && -n "$SERVER_PID" ]]; then
    log "Stopping test server (pid $SERVER_PID)"
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

: >"$SUMMARY_FILE"
log "README retest started at $(date -u)"
log "Project: $ROOT"
log "Log file: $LOG_FILE"
log "Summary: $SUMMARY_FILE"
log "BASE_URL: $BASE_URL"

# --- Local run (README) ---
section "1. Prerequisites"
run_step "1.1" "uv --version" uv --version
run_step "1.2" "python version via uv" uv run python -V

section "2. Manual local: uv sync"
unset CHROMA_HOST
export CHROMA_HOST=
run_step "2.1" "uv sync" uv sync

section "3. Start server (if not running)"
SERVER_OK=1
start_server_if_needed || {
  log "FATAL: could not reach server — skipping API tests"
  echo "FAIL  3.0  start_server" >>"$SUMMARY_FILE"
  FAIL=$((FAIL + 1))
  SERVER_OK=0
}

if [[ "$SERVER_OK" -eq 0 ]]; then
  section "4-9. API tests"
  for sid in 4.1 4.2 4.3 5.1 6.1 6.2 7.1 7.2 9.1; do
    skip_step "$sid" "API test" "server not running"
  done
else
section "4. Health + docs"
run_step "4.1" "GET /health" curl "${CURL_OPTS[@]}" "$BASE_URL/health"
run_step "4.2" "GET /docs (OpenAPI)" curl "${CURL_OPTS[@]}" -o /dev/null -w "HTTP %{http_code}\n" "$BASE_URL/docs"
run_step "4.3" "GET /openapi.json" curl "${CURL_OPTS[@]}" -o /dev/null -w "HTTP %{http_code}\n" "$BASE_URL/openapi.json"

section "5. Plain generation"
run_step "5.1" "POST /generate direct" \
  curl "${CURL_OPTS[@]}" -X POST "$BASE_URL/generate" \
    -H "Content-Type: application/json" \
    -d '{"text": "Once upon a time,"}'

section "6. RAG ingest"
run_step "6.1" "ingest_docs.py module" uv run python -m scripts.ingest_docs data/sample_docs
run_step "6.2" "POST /rag/ingest (manual curl)" \
  curl "${CURL_OPTS[@]}" -X POST "$BASE_URL/rag/ingest" \
    -H "Content-Type: application/json" \
    -d '{"text": "ChromaDB stores embeddings for semantic search.", "source": "manual"}'

section "7. RAG ask"
run_step "7.1" "POST /rag/ask (README question)" \
  curl "${CURL_OPTS[@]}" -X POST "$BASE_URL/rag/ask" \
    -H "Content-Type: application/json" \
    -d '{"question": "What is ChromaDB used for?"}'
run_step "7.2" "POST /rag/ask (generic RAG question)" \
  curl "${CURL_OPTS[@]}" -X POST "$BASE_URL/rag/ask" \
    -H "Content-Type: application/json" \
    -d '{"question": "How does a RAG pipeline use ChromaDB?"}'

section "9. Health after all tests"
run_step "9.1" "GET /health (final)" curl "${CURL_OPTS[@]}" "$BASE_URL/health"
fi

section "10. Docker run (optional)"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  run_step "10.1" "docker compose config" docker compose config
  log "Docker full stack test skipped by default (slow, port conflict). Set RUN_DOCKER=1 to enable."
  if [[ "${RUN_DOCKER:-0}" == "1" ]]; then
    run_step "10.2" "docker compose up --build -d" docker compose up --build -d
    run_step "10.3" "docker health localhost:8000" \
      curl "${CURL_OPTS[@]}" http://localhost:8000/health
    run_step "10.4" "docker compose ingest" \
      docker compose -f docker-compose.yml -f docker-compose.ingest.yml run --rm ingest
    run_step "10.5" "docker compose down" docker compose down
  else
    skip_step "10.2" "docker compose up" "RUN_DOCKER!=1"
    skip_step "10.3" "docker ingest" "RUN_DOCKER!=1"
  fi
else
  skip_step "10.0" "docker available" "docker not running or not installed"
fi

section "SUMMARY"
log "PASS: $PASS  FAIL: $FAIL  SKIP: $SKIP"
log "Full log: $LOG_FILE"
log "Summary: $SUMMARY_FILE"
cat "$SUMMARY_FILE" | tee -a "$LOG_FILE"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
