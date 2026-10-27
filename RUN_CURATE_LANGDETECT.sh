#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
"$PYTHON" 'scripts/curate_meajor.py' '--policy' 'readability' '--label' '1' '--input' 'data/meajor_cleaned_preprocessed.csv' '--output-dir' 'outputs/quality_langdetect_diagnostic_v2' '--provider' 'langdetect' "$@"
