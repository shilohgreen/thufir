"""
agent/supabase_client.py — Readonly Supabase client for the Thufir agent.
"""
from __future__ import annotations

import json
import logging

from supabase import create_client, Client

from agent.config import SUPABASE_URL, SUPABASE_KEY, MAX_RESULT_CHARS

logger = logging.getLogger(__name__)


def get_client() -> Client:
    """Create and return a Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


async def list_tables(client: Client) -> str:
    """Fetch available tables and their columns via information_schema."""
    try:
        result = client.rpc(
            "get_schema_info",
            {},
        ).execute()
        return json.dumps(result.data, indent=2)
    except Exception as e:
        logger.warning(f"[ ⚠️ list_tables ] RPC get_schema_info failed: {e}")
        return "(Could not fetch schema info — make sure the get_schema_info RPC exists)"


async def execute_query(client: Client, action: dict) -> str:
    """Execute a readonly query based on the agent's action dict."""
    table = action.get("table", "")
    select = action.get("select", "*")
    filters = action.get("filters", [])
    limit = action.get("limit", 100)

    logger.info(f"[ 🔍 execute_query ] table={table}, select={select}, filters={filters}, limit={limit}")

    query = client.table(table).select(select)

    # Apply filters
    for f in filters:
        col = f.get("column", "")
        op = f.get("op", "eq")
        val = f.get("value")

        if op == "eq":
            query = query.eq(col, val)
        elif op == "neq":
            query = query.neq(col, val)
        elif op == "gt":
            query = query.gt(col, val)
        elif op == "gte":
            query = query.gte(col, val)
        elif op == "lt":
            query = query.lt(col, val)
        elif op == "lte":
            query = query.lte(col, val)
        elif op == "like":
            query = query.like(col, val)
        elif op == "ilike":
            query = query.ilike(col, val)
        elif op == "in":
            query = query.in_(col, val)
        elif op == "is":
            query = query.is_(col, val)
        else:
            logger.warning(f"[ ⚠️ execute_query ] Unknown operator: {op}")

    query = query.limit(limit)
    result = query.execute()

    text = json.dumps(result.data, indent=2, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n…[truncated]"

    return text


async def execute_rpc(client: Client, action: dict) -> str:
    """Execute a readonly RPC function call."""
    function = action.get("function", "")
    params = action.get("params", {})

    logger.info(f"[ 🔍 execute_rpc ] function={function}, params={params}")

    result = client.rpc(function, params).execute()

    text = json.dumps(result.data, indent=2, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n…[truncated]"

    return text

