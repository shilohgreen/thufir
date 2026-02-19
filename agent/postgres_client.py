"""
agent/postgres_client.py — Readonly Postgres client for the Thufir agent.

Connects directly to any PostgreSQL instance via asyncpg.
"""
from __future__ import annotations

import json
import logging
import re

import asyncpg

from agent.config import DATABASE_URL, MAX_RESULT_CHARS

logger = logging.getLogger(__name__)

# ── SQL safety ────────────────────────────────────────────────────────────────

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)


def _validate_readonly(query: str):
    """Raise if the query contains write/DDL keywords."""
    stripped = query.strip().rstrip(";")
    if _FORBIDDEN.search(stripped):
        raise ValueError(f"Query rejected — only SELECT statements are allowed.")
    if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
        raise ValueError(f"Query rejected — must start with SELECT or WITH (CTE).")


# ── Connection ────────────────────────────────────────────────────────────────

async def get_pool() -> asyncpg.Pool:
    """Create and return a connection pool."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be set in .env")
    return await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)


# ── Schema discovery ─────────────────────────────────────────────────────────

async def list_tables(pool: asyncpg.Pool) -> str:
    """Fetch available tables and their columns from information_schema."""
    query = """
        SELECT
            table_name,
            json_agg(json_build_object(
                'column', column_name,
                'type', data_type
            )) AS columns
        FROM information_schema.columns
        WHERE table_schema = 'public'
        GROUP BY table_name
        ORDER BY table_name;
    """
    try:
        rows = await pool.fetch(query)
        result = [
            {"table_name": row["table_name"], "columns": json.loads(row["columns"])}
            for row in rows
        ]
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.warning(f"[ ⚠️ list_tables ] Schema query failed: {e}")
        return "(Could not fetch schema info)"


# ── Query execution ──────────────────────────────────────────────────────────

async def execute_sql(pool: asyncpg.Pool, action: dict) -> str:
    """Execute a readonly SQL query and return JSON results."""
    query = action.get("query", "")

    logger.info(f"[ 🔍 execute_sql ] {query[:200]}")

    _validate_readonly(query)

    rows = await pool.fetch(query)

    # Convert asyncpg Records to dicts
    result = [dict(row) for row in rows]
    text = json.dumps(result, indent=2, default=str)

    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n…[truncated]"

    return text

