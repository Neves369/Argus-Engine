#!/usr/bin/env bash
set -euo pipefail
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1 | tee /tmp/argus-e2e/backend-console.log