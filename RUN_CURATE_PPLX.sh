#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
"$PYTHON" 'scripts/curate_meajor.py' '--label' '1' '--input' 'data/meajor_cleaned_preprocessed.csv' '--output-dir' 'outputs/quality_pplx_label1' '--provider' 'ollama' '--model' 'pplx-decider:latest' '--base-url' 'http://127.0.0.1:11435' "$@"
