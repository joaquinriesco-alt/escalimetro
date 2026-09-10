#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
export PYTHONPATH=src
for B in EQUILIBRADO DENSO EJECUTIVO; do
  echo "===== BRIEF_$B ====="; T0=$(date +%s)
  python3 -m escalimetro.layout.e07.run --case cases/001_gps_403 --brief briefs/BRIEF_$B.json --out-name E25_$B 2>&1
  echo "===== FIN BRIEF_$B (exit $?, $(( $(date +%s) - T0 )) s) ====="
done
echo "LISTO"
