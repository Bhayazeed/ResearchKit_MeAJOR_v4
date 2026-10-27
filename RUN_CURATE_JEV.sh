#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
[[ -n "${OPENROUTER_API_KEY:-}" ]] || { echo "ERROR: OPENROUTER_API_KEY missing" >&2; exit 1; }
"$PYTHON" 'scripts/curate_meajor.py' '--policy' 'english_length' '--min-words' '101' '--label' '1' '--input' 'data/meajor_cleaned_preprocessed.csv' '--output-dir' 'outputs/quality_jev_english_length_v3' '--provider' 'openrouter' '--model' 'typesafe/jev-1.14' "$@"
