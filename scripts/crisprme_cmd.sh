#!/usr/bin/env bash
# Run `crisprme.py <args...>` through whichever runtime this data directory is configured for
# (Apptainer/Singularity image, Docker image, or a native conda env), so every other script and
# the skill itself can call CRISPRme the same way regardless of how it was installed.
#
# Must be run FROM the CRISPRme data directory (the folder holding Genomes/, Results/, runs/...).
# For container runtimes that folder is mounted at /DATA and used as the working directory, so
# paths passed to CRISPRme must live inside it: relative paths are used as-is, absolute paths
# under the data directory are rewritten to /DATA/..., and absolute paths outside it are refused
# (the container could not see them).
#
# Runtime config: ./.crisprme_runtime (written by install_crisprme.sh), KEY=VALUE lines:
#   RUNTIME=apptainer|docker|native
#   IMAGE=<.sif path (apptainer) | image tag (docker)>
#   CONDA_ENV_PREFIX=<env prefix (native)>
# Environment variables of the same names override the file.
#
# Usage: crisprme_cmd.sh <crisprme.py args...>
#        crisprme_cmd.sh --exec <program> [args...]   (run another tool from the same runtime,
#                                                       e.g. crispritz.py or hf)
#        crisprme_cmd.sh --show-runtime     (print the resolved runtime and exit)
set -euo pipefail

CONFIG_FILE=".crisprme_runtime"

conf_get() {
  [ -f "$CONFIG_FILE" ] || return 0
  grep -E "^$1=" "$CONFIG_FILE" | tail -n 1 | cut -d= -f2- || true
}

RUNTIME="${RUNTIME:-$(conf_get RUNTIME)}"
IMAGE="${IMAGE:-$(conf_get IMAGE)}"
CONDA_ENV_PREFIX="${CONDA_ENV_PREFIX:-$(conf_get CONDA_ENV_PREFIX)}"

if [ -z "$RUNTIME" ]; then
  cat >&2 <<EOF
No CRISPRme runtime configured for $(pwd) (no $CONFIG_FILE here).
Either cd into your CRISPRme data directory, or set one up with:
  scripts/install_crisprme.sh            (pulls the container image and writes $CONFIG_FILE)
EOF
  exit 1
fi

if [ "${1:-}" = "--show-runtime" ]; then
  echo "runtime: $RUNTIME"
  if [ -n "$IMAGE" ]; then echo "image:   $IMAGE"; fi
  if [ -n "$CONDA_ENV_PREFIX" ]; then echo "env:     $CONDA_ENV_PREFIX"; fi
  echo "datadir: $(pwd)"
  exit 0
fi

DATA_DIR="$(pwd -P)"

PROGRAM=crisprme.py
if [ "${1:-}" = "--exec" ]; then
  [ "$#" -ge 2 ] || { echo "Usage: $0 --exec <program> [args...]" >&2; exit 1; }
  PROGRAM="$2"
  shift 2
fi

# Container runtimes only see the data directory (as /DATA): translate or refuse absolute paths.
map_args() {
  MAPPED=()
  local arg
  for arg in "$@"; do
    case "$arg" in
      "$DATA_DIR") MAPPED+=("/DATA") ;;
      "$DATA_DIR"/*) MAPPED+=("/DATA/${arg#"$DATA_DIR"/}") ;;
      "$PWD") MAPPED+=("/DATA") ;;
      "$PWD"/*) MAPPED+=("/DATA/${arg#"$PWD"/}") ;;
      /DATA|/DATA/*) MAPPED+=("$arg") ;;
      /*)
        if [ -e "$arg" ]; then
          echo "Path '$arg' is outside the data directory ($DATA_DIR) and would not be visible" \
               "inside the container. Copy it into the data directory first (a symlink pointing" \
               "outside would not resolve inside the container either)." >&2
          exit 1
        fi
        MAPPED+=("$arg") ;;
      *) MAPPED+=("$arg") ;;
    esac
  done
}

# Host variables the container should see: an HF token (rate limits) and CRISPRme's own tuning
# knobs (CRISPRME_MAX_MEM_GB, CRISPRME_INDEL_SNP, ...). Nothing else is passed through.
FORWARD_VARS=()
for v in HF_TOKEN $(compgen -e | grep -E '^CRISPRME_' || true); do
  if [ -n "${!v:-}" ]; then FORWARD_VARS+=("$v"); fi
done

case "$RUNTIME" in
  apptainer)
    APPT="$(command -v apptainer || command -v singularity || true)"
    [ -n "$APPT" ] || { echo "Neither apptainer nor singularity is on PATH." >&2; exit 1; }
    [ -f "$IMAGE" ] || { echo "Apptainer image '$IMAGE' not found (see $CONFIG_FILE)." >&2; exit 1; }
    map_args "$@"
    # --cleanenv: host variables must not leak in (e.g. a host SSL_CERT_FILE path that doesn't
    # exist in the image breaks every HTTPS download). Variables are set via APPTAINERENV_* /
    # SINGULARITYENV_*, which survive --cleanenv and handle any value safely. HF_HOME keeps the
    # HuggingFace cache on the data disk, not a small $HOME; PYTHONNOUSERSITE stops packages in
    # the (auto-mounted) host ~/.local leaking in.
    set_cenv() { export "APPTAINERENV_$1=$2" "SINGULARITYENV_$1=$2"; }
    set_cenv HF_HOME /DATA/.hf_cache
    set_cenv PYTHONNOUSERSITE 1
    for v in ${FORWARD_VARS[@]+"${FORWARD_VARS[@]}"}; do set_cenv "$v" "${!v}"; done
    # `run` (not `exec`): the image's runscript activates the conda env that puts crisprme.py on PATH.
    exec "$APPT" run --cleanenv --bind "$DATA_DIR:/DATA" --pwd /DATA \
      "$IMAGE" "$PROGRAM" ${MAPPED[@]+"${MAPPED[@]}"}
    ;;
  docker)
    command -v docker >/dev/null 2>&1 || { echo "docker is not on PATH." >&2; exit 1; }
    [ -n "$IMAGE" ] || { echo "No docker IMAGE set in $CONFIG_FILE." >&2; exit 1; }
    map_args "$@"
    ENV_ARGS=(-e HF_HOME=/DATA/.hf_cache)
    for v in ${FORWARD_VARS[@]+"${FORWARD_VARS[@]}"}; do ENV_ARGS+=(-e "$v"); done
    exec docker run --rm -i -v "$DATA_DIR:/DATA" -w /DATA "${ENV_ARGS[@]}" \
      "$IMAGE" "$PROGRAM" ${MAPPED[@]+"${MAPPED[@]}"}
    ;;
  native)
    [ -x "$CONDA_ENV_PREFIX/bin/crisprme.py" ] || {
      echo "No crisprme.py in conda env '$CONDA_ENV_PREFIX' (see $CONFIG_FILE)." >&2; exit 1; }
    # `conda run` puts the env's bin/ (crispritz.py, bcftools, ...) on PATH without activation.
    exec conda run --no-capture-output -p "$CONDA_ENV_PREFIX" "$PROGRAM" "$@"
    ;;
  *)
    echo "Unknown RUNTIME '$RUNTIME' in $CONFIG_FILE (expected apptainer, docker or native)." >&2
    exit 1
    ;;
esac
