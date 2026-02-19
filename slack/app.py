#!/usr/bin/env python3
"""
slack/app.py — Entrypoint for the Thufir Slack bot (HTTP mode).

Uses Bolt for Python (async) with FastAPI so it can run serverless on Cloud Run.
Slack sends events as HTTP POST requests — no persistent WebSocket needed.

Usage (local):
    uvicorn slack.app:fastapi_app --host 0.0.0.0 --port 3000

Required env vars:
    SLACK_BOT_TOKEN      — xoxb-… bot token
    SLACK_SIGNING_SECRET — signing secret (from Slack app → Basic Information)
    THUFIR_API_URL       — base URL of the deployed Thufir Cloud Run service
"""
from __future__ import annotations

import logging
import sys

from fastapi import FastAPI, Request
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from slack.config import SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, THUFIR_API_URL
from slack.handlers import register_handlers

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Validate env ──────────────────────────────────────────────────────────────

def _check_env():
    missing = []
    if not SLACK_BOT_TOKEN:
        missing.append("SLACK_BOT_TOKEN")
    if not SLACK_SIGNING_SECRET:
        missing.append("SLACK_SIGNING_SECRET")
    if missing:
        logger.error(f"Missing required env vars: {', '.join(missing)}")
        sys.exit(1)


# ── Bolt app (async, HTTP mode) ──────────────────────────────────────────────

_check_env()

bolt_app = AsyncApp(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET,
)
register_handlers(bolt_app)
logger.info("[ ✅ slack/app ] Bolt app created and handlers registered (HTTP mode)")

# ── FastAPI wrapper ───────────────────────────────────────────────────────────

fastapi_app = FastAPI(title="Thufir Slack Bot", description="Slack bot for the Thufir agent")
handler = AsyncSlackRequestHandler(bolt_app)


@fastapi_app.get("/health")
async def health():
    return {"status": "ok"}


@fastapi_app.post("/slack/events")
async def slack_events(req: Request):
    """Handle all Slack events, commands, and interactions."""
    return await handler.handle(req)


@fastapi_app.post("/slack/commands")
async def slack_commands(req: Request):
    """Handle slash commands (if configured with a separate URL)."""
    return await handler.handle(req)


@fastapi_app.post("/slack/interactions")
async def slack_interactions(req: Request):
    """Handle interactive components (buttons, modals, etc.)."""
    return await handler.handle(req)


logger.info(f"[ 🚀 slack/app ] Thufir Slack bot ready (HTTP mode)")
logger.info(f"   Thufir API: {THUFIR_API_URL}")

