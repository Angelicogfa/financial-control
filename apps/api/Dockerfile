FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock* .python-version ./
COPY packages/core ./packages/core
COPY packages/persistence ./packages/persistence
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker

RUN uv sync --all-packages --no-dev

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "fincontrol_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
