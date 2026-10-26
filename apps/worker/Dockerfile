# syntax=docker/dockerfile:1.7
# Worker image. Multi-stage: dependencies are resolved with uv in the builder; the runtime
# has no build tools, ships no API code and runs as an unprivileged user.

FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# Only the manifest of the API is needed to load the workspace; its code is not shipped.
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/packages/config apps/packages/config
COPY apps/packages/core apps/packages/core
COPY apps/packages/persistence apps/packages/persistence
COPY apps/worker apps/worker

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package fincontrol-worker

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder /app /app

USER app

CMD ["python", "-m", "fincontrol_worker.scheduler"]
