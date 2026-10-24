# syntax=docker/dockerfile:1.7
# API image (also used by the `migrate` service). Multi-stage: dependencies are resolved
# with uv in the builder; the runtime has no build tools and runs as an unprivileged user.

FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# Only the manifest of the worker is needed to load the workspace; its code is not shipped.
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/config packages/config
COPY packages/core packages/core
COPY packages/persistence packages/persistence
COPY apps/api apps/api

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package fincontrol-api

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]

CMD ["uvicorn", "fincontrol_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
