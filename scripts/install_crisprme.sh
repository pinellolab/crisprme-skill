#!/usr/bin/env bash
# Set up a CRISPRme+ runtime for the current directory (which becomes the CRISPRme data directory)
# and record it in ./.crisprme_runtime so scripts/crisprme_cmd.sh knows how to call CRISPRme.
#
# Default: the official container image (pinellolab/crisprme:<version>) — upstream's recommended
# install for CRISPRme+ (Bioconda's `crisprme` package is still the old 2.1.x line). Uses Docker
# when a Docker daemon is reachable, otherwise Apptainer/Singularity (typical on HPC, no root).
#
# Usage (run from the data directory):
#   install_crisprme.sh [--runtime docker|apptainer|native] [--version v2.7.9]
#                       [--sif <existing .sif>] [--env-prefix <conda env prefix>] [--force]
#   --sif         reuse an already-pulled Apptainer image instead of pulling a new one
#   --env-prefix  (native) an existing conda env with CRISPRme+ installed from source
#   --force       overwrite an existing ./.crisprme_runtime
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE=".crisprme_runtime"
VERSION="v2.7.9"
RUNTIME=""
SIF=""
ENV_PREFIX=""
FORCE=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --runtime) RUNTIME="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --sif) SIF="$2"; shift 2 ;;
    --env-prefix) ENV_PREFIX="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *) echo "Unknown option '$1'." >&2; exit 1 ;;
  esac
done

if [ -f "$CONFIG_FILE" ] && [ "$FORCE" -eq 0 ]; then
  echo "This directory already has a CRISPRme runtime configured ($CONFIG_FILE):"
  "$SCRIPT_DIR/crisprme_cmd.sh" --show-runtime
  echo "Not changing it. Re-run with --force to replace it."
  exit 0
fi

APPT="$(command -v apptainer || command -v singularity || true)"
if [ -z "$RUNTIME" ]; then
  if [ -n "$SIF" ]; then
    RUNTIME=apptainer
  elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    RUNTIME=docker
  elif [ -n "$APPT" ]; then
    RUNTIME=apptainer
  else
    cat >&2 <<EOF
No usable container runtime found (no reachable Docker daemon, no apptainer/singularity).
Options: install Docker Desktop (laptop/workstation), ask your cluster admins for Apptainer, or
install CRISPRme+ from source into a conda env and re-run with --runtime native --env-prefix <env>.
EOF
    exit 1
  fi
fi

case "$RUNTIME" in
  docker)
    IMAGE="pinellolab/crisprme:$VERSION"
    echo "Pulling $IMAGE ..."
    docker pull "$IMAGE"
    ;;
  apptainer)
    [ -n "$APPT" ] || { echo "Neither apptainer nor singularity is on PATH." >&2; exit 1; }
    if [ -n "$SIF" ]; then
      [ -f "$SIF" ] || { echo "Image '$SIF' not found." >&2; exit 1; }
      IMAGE="$(cd "$(dirname "$SIF")" && pwd -P)/$(basename "$SIF")"
    else
      IMAGE="$(pwd -P)/crisprme_${VERSION}.sif"
      if [ -f "$IMAGE" ]; then
        echo "Reusing existing image $IMAGE"
      else
        echo "Pulling docker://pinellolab/crisprme:$VERSION -> $IMAGE (~4.9 GB, ~10-15 min) ..."
        "$APPT" pull "$IMAGE" "docker://pinellolab/crisprme:$VERSION"
      fi
    fi
    ;;
  native)
    [ -n "$ENV_PREFIX" ] || { echo "--runtime native needs --env-prefix <conda env prefix>." >&2; exit 1; }
    [ -x "$ENV_PREFIX/bin/crisprme.py" ] || { echo "No crisprme.py in '$ENV_PREFIX/bin'." >&2; exit 1; }
    IMAGE=""
    ;;
  *) echo "Unknown runtime '$RUNTIME' (expected docker, apptainer or native)." >&2; exit 1 ;;
esac

{
  echo "RUNTIME=$RUNTIME"
  if [ -n "$IMAGE" ]; then echo "IMAGE=$IMAGE"; fi
  if [ -n "$ENV_PREFIX" ]; then echo "CONDA_ENV_PREFIX=$ENV_PREFIX"; fi
} > "$CONFIG_FILE"

ver="$("$SCRIPT_DIR/crisprme_cmd.sh" --version 2>&1 | tail -n 1)" || ver=""
echo
echo "CRISPRme runtime recorded in $(pwd -P)/$CONFIG_FILE:"
"$SCRIPT_DIR/crisprme_cmd.sh" --show-runtime
echo "crisprme.py --version: ${ver:-<failed — check the runtime above>}"
case "$ver" in
  v2.[01].*) echo "WARNING: this is the legacy 2.1.x line, not CRISPRme+ (2.2+). The skill assumes CRISPRme+." ;;
  v2.[2-5].*) echo "WARNING: CRISPRme+ older than 2.6 (old search defaults, CRISTA scorer, retired default index). The skill is written for 2.7.x." ;;
esac

cat <<EOF

Next steps (run from this directory):
  - Quick check: scripts/crisprme_cmd.sh --help
  - Reference data (hg38 + annotations + PAMs + the NRG_3_hg38 reference index, ~26 GB):
      scripts/run_crisprme_job.sh download dl-ref --what all --path .
  - Then ONE variant index for variant-aware searches (default shown; ~87 GB more):
      scripts/run_crisprme_job.sh download dl-index --what index \\
        --index-name NRG_3_hg38+hg38_HGDP1kGP --path .
  - Smoke test once an index is present: scripts/run_crisprme_job.sh complete-test smoke-1
EOF
