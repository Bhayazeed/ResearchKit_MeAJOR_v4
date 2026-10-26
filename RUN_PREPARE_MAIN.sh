#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
"$PYTHON" 'scripts/prepare_meajor.py' '--input' 'data/meajor_cleaned_preprocessed.csv' '--output' 'data/meajor_main_3000.csv' '--per-class' '1500' "$@"
