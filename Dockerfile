# Stage 1: Base Python setup
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS python-base
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT="/venv"
ENV PATH="/venv/bin:$PATH"
WORKDIR /app

# Stage 2: Builder Base
FROM python-base AS builder-base
# Copy only files needed for dependency resolution first
COPY uv.lock pyproject.toml /app/

# Stage 3: Test Builder (Installs ALL dependencies)
FROM builder-base AS test-builder
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev --extra test --no-install-project

# Install project source into test env
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra dev --extra test

# Stage 4: Production Builder (Installs ONLY runtime dependencies)
FROM builder-base AS prod-builder
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Install project source into prod env
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Stage 5: Test Runtime (Uses test-builder venv)
FROM python:3.12-slim-bookworm AS test
WORKDIR /app
COPY --from=test-builder /venv /venv
ENV PATH="/venv/bin:$PATH"
COPY --from=test-builder /app /app
RUN cp /app/entrypoint.sh /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["sh", "/usr/local/bin/entrypoint.sh"]
CMD ["pytest"]

# Stage 6: Production Runtime (Uses prod-builder venv)
FROM python:3.12-slim-bookworm AS production
WORKDIR /app

# Install runtime dependencies (e.g. curl for healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY --from=prod-builder /venv /venv
ENV PATH="/venv/bin:$PATH"
COPY --from=prod-builder /app /app
RUN cp /app/entrypoint.sh /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["sh", "/usr/local/bin/entrypoint.sh"]
EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
