#!/usr/bin/env bash
set -euo pipefail

# Tune macOS network limits, start the API server with multiple workers, and run
# a distributed Locust load with one master and N workers on localhost.
#
# Usage: ./scripts/tune_and_run_locust.sh
# You need sudo for the sysctl changes; they are temporary (not persisted).

USERS=${USERS:-5000}
SPAWN_RATE=${SPAWN_RATE:-50}
RUNTIME=${RUNTIME:-120s}
PORT=${PORT:-8200}
GRANIAN_WORKERS=${GRANIAN_WORKERS:-4}
LOCUST_WORKERS=${LOCUST_WORKERS:-4}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MASTER_LOG="${MASTER_LOG:-/tmp/locust_master.log}"
WORKER_LOG_PREFIX="${WORKER_LOG_PREFIX:-/tmp/locust_worker}"

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script is tailored for macOS (Darwin). Adjust sysctls for your OS before running."
  exit 1
fi

echo "Setting file descriptor limit (soft/hard) to 65535"
ulimit -n 65535

echo "Applying sysctl tuning (requires sudo)..."
sudo sysctl -w kern.ipc.somaxconn=4096
sudo sysctl -w net.inet.ip.portrange.first=1024
sudo sysctl -w net.inet.ip.portrange.last=65535
sudo sysctl -w net.inet.tcp.msl=1000

echo "Starting Granian with ${GRANIAN_WORKERS} workers on port ${PORT}..."
cd "${ROOT_DIR}"
uv run granian \
  --interface asgi \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --workers "${GRANIAN_WORKERS}" \
  app:app >/dev/null 2>&1 &
PIDS=($!)
sleep 3

echo "Starting Locust master (expecting ${LOCUST_WORKERS} workers)..."
uv run locust -f locustfile.py \
  --master \
  --expect-workers "${LOCUST_WORKERS}" \
  --headless \
  -u "${USERS}" \
  -r "${SPAWN_RATE}" \
  -t "${RUNTIME}" \
  --host "http://127.0.0.1:${PORT}" \
  --loglevel INFO >"${MASTER_LOG}" 2>&1 &
MASTER_PID=$!
PIDS+=("${MASTER_PID}")
sleep 3

echo "Starting ${LOCUST_WORKERS} Locust workers..."
for i in $(seq 1 "${LOCUST_WORKERS}"); do
  uv run locust -f locustfile.py \
    --worker \
    --master-host 127.0.0.1 \
    --master-port 5557 \
    --loglevel INFO >"${WORKER_LOG_PREFIX}_${i}.log" 2>&1 &
  PIDS+=($!)
done

echo "Load test running (master PID ${MASTER_PID}); tailing master log:"
tail -n 5 -f "${MASTER_LOG}" &
TAIL_PID=$!
wait "${MASTER_PID}" || true
kill "${TAIL_PID}" 2>/dev/null || true

echo "Done. Master log: ${MASTER_LOG}"
