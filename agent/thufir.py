#!/usr/bin/env python3
"""
thufir.py — CLI entrypoint for the Supabase data-retrieval agent.

Usage:
    python thufir.py --prompt "How many users signed up this week?"
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from agent.config import DEFAULT_ENDPOINT, DEFAULT_MODEL, DEFAULT_API_KEY
from agent.agent import DataAgent
from agent.supabase_client import get_client, list_tables, execute_query, execute_rpc


# ── Main loop ────────────────────────────────────────────────────────────────

async def run_agent(
    prompt: str,
    endpoint: str,
    model: str,
    api_key: str = "no-key",
    max_steps: int = 10,
):
    agent = DataAgent(endpoint, model, api_key)
    client = get_client()

    # Fetch schema info so the agent knows what tables are available
    schema_info = await list_tables(client)

    print(f"\n{'═'*60}")
    print(f"  Available Schema")
    print(f"{'═'*60}\n")
    print(schema_info)
    print(f"\n{'═'*60}\n")

    for step in range(1, max_steps + 1):
        user_msg = (
            f"GOAL: {prompt}\n\n"
            f"Available tables/columns:\n{schema_info}"
        )

        # After the first step, include the query results
        if step > 1:
            user_msg = f"GOAL: {prompt}\n\nPrevious query returned data. Decide what to do next."

        print(f"\n{'─'*60}")
        print(f"  Step {step}/{max_steps}")

        raw = agent.chat(user_msg)

        action = agent.parse_action(raw)
        if action is None:
            print(f"  ⚠️  Could not parse action:\n{raw[:300]}")
            continue

        act = action.get("action")
        reason = action.get("reason", "")
        print(f"  Action: {act}  —  {reason}")

        try:
            if act == "answer":
                result = action.get("text", "")
                print(f"\n{'═'*60}")
                print(f"  ✅  AGENT ANSWER:\n\n{result}")
                print(f"{'═'*60}\n")
                return result

            elif act == "query":
                data = await execute_query(client, action)
                print(f"  📊  Query returned {len(data)} chars of data")
                agent.history.append(
                    {"role": "user", "content": f"Query result:\n{data}"}
                )

            elif act == "rpc":
                data = await execute_rpc(client, action)
                print(f"  📊  RPC returned {len(data)} chars of data")
                agent.history.append(
                    {"role": "user", "content": f"RPC result:\n{data}"}
                )

            else:
                print(f"  ⚠️  Unknown action: {act}")

        except Exception as e:
            err_msg = f"Action '{act}' failed: {e}"
            print(f"  ❌  {err_msg}")
            agent.add_error(err_msg)

    print(f"\n⚠️  Reached max steps ({max_steps}) without an answer.")
    return None


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Supabase data-retrieval agent powered by an OpenAI-compatible LLM."
    )
    parser.add_argument("--prompt", required=True, help="Goal / task for the agent")
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"OpenAI-compatible API base URL (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key")
    parser.add_argument(
        "--max-steps", type=int, default=10, help="Max interaction steps (default: 10)"
    )

    args = parser.parse_args()

    result = asyncio.run(
        run_agent(
            prompt=args.prompt,
            endpoint=args.endpoint,
            model=args.model,
            api_key=args.api_key,
            max_steps=args.max_steps,
        )
    )

    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()

