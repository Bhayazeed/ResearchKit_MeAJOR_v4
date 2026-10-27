#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python; else PYTHON=python3; fi
"$PYTHON" 'scripts/run_baseline.py' '--require-curated' '--label' '1' '--input' 'outputs/quality_pplx_english_length_v3/quality_accepted.csv' '--output-dir' 'outputs/curated_english_length_baseline' '--dry-run' "$@"
