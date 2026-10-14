#!/usr/bin/env bash
# Report every existing CRISPRme install this user could reuse instead of setting up a new one:
# a runtime already configured for the current directory, pulled container images (Docker images,
# Apptainer .sif files under the given search dirs), and conda envs with crisprme.py (all envs,
# not just ones named "crisprme"). Flags the legacy 2.1.x line vs CRISPRme+ (2.2+).
# Read-only — does not activate, pull or modify anything.
# Usage: find_existing_crisprme_installs.sh [dir-to-search-for-.sif ...]   (default: .)
# (Not $HOME by default: walking a home directory on a network filesystem can take minutes.)
set -euo pipefail

line_of() {  # classify a version string
  case "$1" in
    v2.[01].*|2.[01].*) echo "legacy 2.1.x (not CRISPRme+)" ;;
    v2.[2-5].*|2.[2-5].*) echo "CRISPRme+, pre-2.6 (old defaults/scorer, retired indexes)" ;;
    v[0-9]*|[0-9]*) echo "CRISPRme+" ;;
    *) echo "version unknown" ;;
  esac
}

echo "== Runtime configured for this directory ($(pwd)) =="
if [ -f .crisprme_runtime ]; then
  cat .crisprme_runtime
else
  echo "none"
fi

echo
echo "== Docker images =="
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  imgs="$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -i crisprme || true)"
  if [ -n "$imgs" ]; then
    while IFS= read -r img; do
      printf "%-40s %s\n" "$img" "$(line_of "${img##*:}")"
    done <<< "$imgs"
  else
    echo "none"
  fi
else
  echo "docker not available"
fi

echo
echo "== Apptainer/Singularity images (.sif) =="
if [ "$#" -eq 0 ]; then set -- .; fi
sifs="$(find "$@" -maxdepth 4 -iname '*crisprme*.sif' 2>/dev/null | sort -u || true)"
if [ -n "$sifs" ]; then
  while IFS= read -r sif; do
    ver="$(basename "$sif" | grep -oE 'v?[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    printf "%-60s %s\n" "$sif" "${ver:-?} $(line_of "$ver")"
  done <<< "$sifs"
else
  echo "none found under: $*"
fi

echo
echo "== Conda envs with crisprme.py =="
if ! command -v conda >/dev/null 2>&1; then
  echo "conda not available"
  exit 0
fi
FOUND=0
while IFS= read -r line; do
  [[ "$line" == \#* || -z "$line" ]] && continue
  path="${line##* }"
  name="${line%% *}"
  bin="$path/bin/crisprme.py"
  py="$path/bin/python"
  [ -f "$bin" ] && [ -x "$py" ] || continue
  FOUND=1
  ver=$("$py" "$bin" --version 2>&1 | tail -1) || ver=""
  case "$ver" in
    v[0-9]*) : ;;
    *) ver="unknown" ;;
  esac
  printf "%-22s %-9s %-41s %s\n" "$name" "$ver" "$(line_of "$ver")" "$path"
done < <(conda env list)
[ "$FOUND" -eq 1 ] || echo "none"
