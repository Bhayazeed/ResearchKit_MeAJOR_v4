#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
[[ -n "${OPENROUTER_API_KEY:-}" ]] || { echo "ERROR: OPENROUTER_API_KEY missing" >&2; exit 1; }
"$PYTHON" 'scripts/curate_meajor.py' '--label' '1' '--input' 'data/meajor_cleaned_preprocessed.csv' '--output-dir' 'outputs/quality_jev_label1' '--provider' 'openrouter' '--model' 'typesafe/jev-1.14' "$@"
