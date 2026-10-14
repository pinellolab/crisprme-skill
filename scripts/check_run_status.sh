#!/usr/bin/env bash
# Report status of a background CRISPRme job started via run_crisprme_job.sh.
# Usage: check_run_status.sh <job_name>
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <output_name>" >&2
  exit 1
fi

OUTPUT_NAME="$1"
RUN_DIR="runs/${OUTPUT_NAME}"
STATUS_FILE="$RUN_DIR/status"
LOG_FILE="$RUN_DIR/run.log"
PID_FILE="$RUN_DIR/pid"

if [ ! -f "$STATUS_FILE" ]; then
  echo "No run found for '$OUTPUT_NAME' (expected $STATUS_FILE)." >&2
  exit 1
fi

echo "status: $(cat "$STATUS_FILE")"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "process: running (pid $PID)"
  else
    echo "process: not running"
  fi
fi

if [ -f "$LOG_FILE" ]; then
  echo "--- last 15 lines of log ---"
  tail -n 15 "$LOG_FILE"
fi
