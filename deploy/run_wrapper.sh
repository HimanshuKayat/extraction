#!/usr/bin/env bash

set -euo pipefail

ROOT="/content/extraction"

cd "$ROOT"

export PYTHONPATH="$ROOT"

if [[ $# -eq 0 ]]; then
    python deploy/run_all.py
else
    python -m "pipelines.$1.run"
fi