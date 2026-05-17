#!/bin/bash

set -e

echo "Starting Enterprise AI-OS..."

export APP_ENV=local
export LOG_LEVEL=INFO
export MAX_TOKENS=8000
export MAX_TOOL_CALLS=10
export REQUEST_TIMEOUT_SECONDS=30
export ENABLE_HUMAN_APPROVAL=true

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
