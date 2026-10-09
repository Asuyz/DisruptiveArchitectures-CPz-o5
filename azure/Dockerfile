# Build a partir da RAIZ do repositório (o rag.py espera ../../scripts/ relativo a api/python)
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/api/python

# Dependências primeiro (melhor cache de camadas)
COPY api/python/pyproject.toml api/python/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Código e índice RAG (mesma estrutura de pastas do repositório)
COPY api/python/chatbot.py api/python/rag.py ./
COPY scripts/chunks_gemini_embedded.json /app/scripts/chunks_gemini_embedded.json

EXPOSE 8000
CMD ["/app/api/python/.venv/bin/uvicorn", "chatbot:app", "--host", "0.0.0.0", "--port", "8000"]
