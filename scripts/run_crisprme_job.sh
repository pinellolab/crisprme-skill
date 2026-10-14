#!/usr/bin/env bash
# Launch a CRISPRme subcommand in the background and track its status via marker files.
# Runs through scripts/crisprme_cmd.sh, so it works the same for container (Apptainer/Docker)
# and native installs. Run from the CRISPRme data directory.
# Usage: run_crisprme_job.sh <subcommand> <job_name> [subcommand flags...]
#        run_crisprme_job.sh exec <job_name> <program> [args...]   (another tool from the same
#        runtime, e.g. crispritz.py index-genome — see crisprme_cmd.sh --exec)
set -euo pipefail

SUBCOMMANDS="complete-search complete-test validate-test assembly-search download build-index-only generate-report generate-personal-card exec"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <${SUBCOMMANDS// /|}> <job_name> [subcommand flags...]" >&2
  exit 1
fi

SUBCOMMAND="$1"
JOB_NAME="$2"
shift 2

case " $SUBCOMMANDS " in
  *" $SUBCOMMAND "*) ;;
  *)
    echo "Unsupported subcommand '$SUBCOMMAND'. Use one of: $SUBCOMMANDS." >&2
    exit 1
    ;;
esac

if [ "$SUBCOMMAND" = exec ] && [ "$#" -lt 1 ]; then
  echo "Usage: $0 exec <job_name> <program> [args...]" >&2
  exit 1
fi

# Fail now (not in the background) if no runtime is configured for this directory.
"$SCRIPT_DIR/crisprme_cmd.sh" --show-runtime >/dev/null

RUN_DIR="runs/${JOB_NAME}"
STATUS_FILE="$RUN_DIR/status"
LOG_FILE="$RUN_DIR/run.log"
PID_FILE="$RUN_DIR/pid"
EXIT_CODE_FILE="$RUN_DIR/exit_code"

if [ -e "$STATUS_FILE" ]; then
  echo "Job '$JOB_NAME' already exists at $RUN_DIR (status: $(cat "$STATUS_FILE")). Pick a different job name to avoid overwriting it." >&2
  exit 1
fi

mkdir -p "$RUN_DIR"
echo "RUNNING" > "$STATUS_FILE"
if [ "$SUBCOMMAND" = exec ]; then
  CMD=(--exec "$@")
else
  CMD=("$SUBCOMMAND" "$@")
fi
echo "${CMD[*]}" > "$RUN_DIR/command"

(
  set +e
  "$SCRIPT_DIR/crisprme_cmd.sh" "${CMD[@]}" > "$LOG_FILE" 2>&1
  code=$?
  echo "$code" > "$EXIT_CODE_FILE"
  # Belt and braces: complete-search now exits non-zero when its pipeline fails, but other
  # subcommands/older versions have exited 0 after an internal failure — also scan the log.
  # complete-test also exits 0 without testing anything when earlier test output exists
  # ("already run once") or when no prebuilt index / its genome is present.
  if [ "$code" -eq 0 ] && ! grep -qE "ERROR:|CRISPRme run failed|Traceback \(most recent call last\)|already run once|No prebuilt index found|CRISPRme does not build data automatically" "$LOG_FILE"; then
    echo "DONE" > "$STATUS_FILE"
  else
    echo "FAILED" > "$STATUS_FILE"
  fi
) &

echo $! > "$PID_FILE"
disown

cat <<EOF
Launched '$SUBCOMMAND' in the background as job '$JOB_NAME'.
  run dir: $RUN_DIR
  pid:     $(cat "$PID_FILE")
  log:     $LOG_FILE
  status:  $STATUS_FILE

Check progress with: scripts/check_run_status.sh $JOB_NAME
EOF
