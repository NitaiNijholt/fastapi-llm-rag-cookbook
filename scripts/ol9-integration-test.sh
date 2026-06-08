#!/usr/bin/env bash
# Oracle Linux 9 integration test: compose up, ingest, RAG, host pytest.
#
# From dev machine (WSL + Docker Desktop):
#   ./scripts/ol9-integration-test.sh
#   ./scripts/ol9-integration-test.sh --resume   # stack already up
#   ./scripts/ol9-integration-test.sh --keep   # leave stack running
#
# On OL9 deploy host with native Docker:
#   RUN_ON_HOST_OL9=1 ./scripts/ol9-integration-test.sh
#
# Logs: logs/ol9_integration_<timestamp>.log
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INNER="${ROOT}/scripts/ol9-run-tests-inner.sh"
IMAGE="${OL9_IMAGE:-oraclelinux:9}"
KEEP_STACK=0
SKIP_COMPOSE_UP=0

mkdir -p "${ROOT}/logs"

for arg in "$@"; do
  case "${arg}" in
    --keep) KEEP_STACK=1 ;;
    --resume) SKIP_COMPOSE_UP=1 ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "unknown arg: ${arg} (try --keep or --resume)" >&2
      exit 2
      ;;
  esac
done

fix_log_permissions() {
  if [[ -d "${ROOT}/logs" ]] && [[ -n "${SUDO_USER:-}" || -w "${ROOT}/logs" ]]; then
    chown -R "$(id -u):$(id -g)" "${ROOT}/logs" 2>/dev/null || \
      sudo chown -R "$(id -u):$(id -g)" "${ROOT}/logs" 2>/dev/null || true
  elif [[ -d "${ROOT}/logs" ]]; then
    sudo chown -R "$(id -u):$(id -g)" "${ROOT}/logs" 2>/dev/null || true
  fi
}

resolve_docker_cli() {
  if [[ ! -S /var/run/docker.sock ]]; then
    echo "error: /var/run/docker.sock missing — start Docker Desktop / Docker daemon" >&2
    exit 1
  fi
  DOCKER_BIN="$(readlink -f "$(command -v docker)")"
  COMPOSE_PLUGIN="/mnt/wsl/docker-desktop/cli-tools/usr/local/lib/docker/cli-plugins/docker-compose"
  if [[ ! -x "${COMPOSE_PLUGIN}" ]]; then
    echo "error: Docker Desktop compose plugin not at ${COMPOSE_PLUGIN}" >&2
    echo "       On OL9 with native docker: RUN_ON_HOST_OL9=1 $0" >&2
    exit 1
  fi
}

run_on_host_ol9() {
  export ROOT KEEP_STACK SKIP_COMPOSE_UP COMPOSE_PROJECT=ol9-integration-test
  export PATH="${HOME}/.local/bin:${PATH}"
  bash "${INNER}"
}

run_in_ol9_container() {
  resolve_docker_cli
  docker pull "${IMAGE}"

  docker run --rm \
    --add-host=host.docker.internal:host-gateway \
    -e ROOT=/work \
    -e KEEP_STACK="${KEEP_STACK}" \
    -e SKIP_COMPOSE_UP="${SKIP_COMPOSE_UP}" \
    -e COMPOSE_PROJECT=ol9-integration-test \
    -v "${ROOT}:/work" \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "${DOCKER_BIN}:/usr/local/bin/docker:ro" \
    -v "${COMPOSE_PLUGIN}:/usr/local/lib/docker/cli-plugins/docker-compose:ro" \
    "${IMAGE}" \
    bash -c 'dnf install -y curl tar gzip which python3 && bash /work/scripts/ol9-run-tests-inner.sh'

  fix_log_permissions
}

if [[ -f /etc/os-release ]] && grep -qE '^ID="?ol' /etc/os-release && [[ "${RUN_ON_HOST_OL9:-}" == "1" ]]; then
  echo "running on host OL9 (RUN_ON_HOST_OL9=1)"
  run_on_host_ol9
elif [[ "${RUN_ON_HOST_OL9:-}" == "1" ]]; then
  echo "RUN_ON_HOST_OL9=1 — running inner script on this host"
  run_on_host_ol9
else
  echo "running inside ${IMAGE} container (mounted host Docker)"
  run_in_ol9_container
fi
