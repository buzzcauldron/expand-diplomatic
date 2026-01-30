#!/bin/sh
# Start Ollama in background, wait until ready, optionally update model, then run expand_diplomatic.
# OLLAMA_MODELS: model dir (baked at build or mounted).
# OLLAMA_UPDATE_MODEL=1: run "ollama pull OLLAMA_MODEL" before expand to keep model updated.

set -e

export OLLAMA_MODELS="${OLLAMA_MODELS:-/app/.ollama}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2}"

ollama serve &
OPID=$!

# Wait for Ollama /api/tags to respond (model dir ready)
i=0
while [ $i -lt 60 ]; do
  if curl -sf "http://${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 1
done
if [ $i -eq 60 ]; then
  echo "Ollama did not become ready in time." >&2
  kill $OPID 2>/dev/null || true
  exit 1
fi

# Optional: keep local Ollama model updated (pull latest before running)
if [ "${OLLAMA_UPDATE_MODEL}" = "1" ] || [ "${OLLAMA_UPDATE_MODEL}" = "true" ] || [ "${OLLAMA_UPDATE_MODEL}" = "yes" ]; then
  echo "Updating Ollama model: $OLLAMA_MODEL"
  ollama pull "$OLLAMA_MODEL" || true
fi

exec python -m expand_diplomatic "$@"
