# expand_diplomatic — multi-arch: linux/amd64, linux/arm64 (Mac, Linux, Windows via WSL2)
# Includes Ollama + default model (llama3.2) for --backend local.
FROM python:3.12-slim-bookworm

WORKDIR /app

# Build args for Ollama (default model baked into image)
ARG OLLAMA_VERSION=0.15.2
ARG OLLAMA_MODEL=llama3.2

# Install deps + Ollama
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl zstd ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN case "$TARGETARCH" in \
    amd64) arch=amd64 ;; \
    arm64) arch=arm64 ;; \
    *) echo "Unsupported TARGETARCH: $TARGETARCH"; exit 1 ;; \
    esac \
    && curl -fSL "https://github.com/ollama/ollama/releases/download/v${OLLAMA_VERSION}/ollama-linux-${arch}.tar.zst" \
    | tar -I zstd -x -C /usr \
    && ollama --version

# Python app (cache pip for faster rebuilds when deps unchanged)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY run_gemini.py examples.json ./
COPY expand_diplomatic/ ./expand_diplomatic/

# Bake Ollama model at build time. Set SKIP_OLLAMA_PULL=1 to skip (faster CI builds).
ENV OLLAMA_MODELS=/app/.ollama
ARG SKIP_OLLAMA_PULL=
RUN mkdir -p /app/.ollama && \
    if [ -z "$SKIP_OLLAMA_PULL" ]; then \
      ollama serve & OPID=$!; sleep 5; \
      i=0; while [ $i -lt 30 ]; do curl -sf http://127.0.0.1:11434/api/tags >/dev/null && break; i=$((i+1)); sleep 2; done; \
      ollama pull "${OLLAMA_MODEL}" || echo "Ollama pull failed; will pull at runtime."; \
      kill $OPID 2>/dev/null || true; sleep 2; \
    else echo "Skipping Ollama model pull."; fi

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV OLLAMA_MODEL=llama3.2
ENV OLLAMA_UPDATE_MODEL=""
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["--help"]
