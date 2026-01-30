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

# Python app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && rm -rf /root/.cache/pip

COPY run_gemini.py examples.json ./
COPY expand_diplomatic/ ./expand_diplomatic/

# Bake Ollama model at build time (OLLAMA_MODELS);
# serve in background, pull model, then stop.
ENV OLLAMA_MODELS=/app/.ollama
RUN mkdir -p /app/.ollama \
    && sh -c 'ollama serve & OPID=$!; sleep 5; \
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do \
      curl -sf http://127.0.0.1:11434/api/tags >/dev/null && break; \
      sleep 2; \
    done; \
    ollama pull "'"${OLLAMA_MODEL}"'"; \
    kill $OPID 2>/dev/null || true; \
    sleep 2'

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
ENV OLLAMA_MODEL=llama3.2
ENV OLLAMA_UPDATE_MODEL=""
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["--help"]
