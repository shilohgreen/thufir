# ── Thufir Slack Bot — Cloud Run Dockerfile ────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies
COPY slack/pyproject.toml slack/pyproject.toml
RUN uv pip install --system --no-cache -r slack/pyproject.toml

# Copy application code
COPY slack/ slack/

# Cloud Run uses PORT env var (defaults to 3000)
ENV PORT=3000

EXPOSE 3000

CMD ["sh", "-c", "uvicorn slack.app:fastapi_app --host 0.0.0.0 --port ${PORT}"]
