# ── Thufir Agent — Cloud Run Dockerfile ────────────────────────────────────────

FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies
COPY agent/pyproject.toml agent/pyproject.toml
RUN uv pip install --system --no-cache -r agent/pyproject.toml

# Copy application code
COPY agent/ agent/

# Cloud Run uses PORT env var (defaults to 8080)
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "uvicorn agent.api:app --host 0.0.0.0 --port ${PORT}"]
