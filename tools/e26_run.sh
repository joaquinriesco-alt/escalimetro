#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
export PYTHONPATH=src
echo "===== GPS 403 · BRIEF_EQUILIBRADO ====="; T0=$(date +%s)
python3 -m escalimetro.layout.e07.run --case cases/001_gps_403 --brief briefs/BRIEF_EQUILIBRADO.json --out-name E26_403 2>&1
echo "===== FIN 403 (exit $?, $(( $(date +%s) - T0 )) s) ====="
echo "===== GPS 401 · BRIEF_401_V1 ====="; T0=$(date +%s)
python3 -m escalimetro.layout.e07.run --case cases/002_gps_401 --brief briefs/BRIEF_401_V1.json --out-name E26_401 2>&1
echo "===== FIN 401 (exit $?, $(( $(date +%s) - T0 )) s) ====="
echo LISTO
