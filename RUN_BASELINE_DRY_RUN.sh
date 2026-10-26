#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
"$PYTHON" 'scripts/run_baseline.py' '--label' '1' '--input' 'data/meajor_cleaned_preprocessed.csv' '--output-dir' 'outputs/label1_baseline' '--dry-run' "$@"
