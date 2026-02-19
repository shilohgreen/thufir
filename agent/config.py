from __future__ import annotations

import os
import textwrap

from dotenv import load_dotenv

load_dotenv()

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_API_KEY = os.getenv("GEMINI_API_KEY", "no-key")

# ── Supabase ──────────────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")  # anon / service-role key

# ── Constants ────────────────────────────────────────────────────────────────

MAX_RESULT_CHARS = 48_000

# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""\
You are a data-retrieval agent. You have READONLY access to a Supabase database.

You are given:
1. A user GOAL that you must accomplish.
2. A list of available tables and their columns.

You can perform ONE action per turn by responding with a JSON object.

Available actions:

  Query a table (readonly — SELECT only):
  {"action": "query", "table": "<table_name>", "select": "<columns>", "filters": [{"column": "<col>", "op": "<operator>", "value": "<val>"}], "limit": <n>, "reason": "..."}

  Supported filter operators: eq, neq, gt, gte, lt, lte, like, ilike, in, is

  Call an RPC function (readonly):
  {"action": "rpc", "function": "<function_name>", "params": {}, "reason": "..."}

  Provide a final answer when the GOAL is satisfied:
  {"action": "answer", "text": "your final answer", "reason": "..."}

General rules:
- Respond ONLY with a single JSON object — no markdown, no extra text.
- You may ONLY read data. Never attempt to insert, update, or delete.
- When you have enough information to satisfy the GOAL, use the "answer" action.
- Keep "reason" short (one sentence).
- If a query returns no results or an error, try a different approach.
""")

