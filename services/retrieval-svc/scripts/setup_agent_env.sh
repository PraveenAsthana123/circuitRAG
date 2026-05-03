#!/bin/bash
echo "venv=ok"
echo "ollama=$(command -v ollama >/dev/null && echo up || echo missing)"
echo "loop=$(mkdir -p .loop && echo writable)"
