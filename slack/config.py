"""
slack/config.py — Environment variables and constants for the Slack bot.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# ── Slack credentials ─────────────────────────────────────────────────────────
# Bot token (xoxb-…) — needs chat:write, app_mentions:read, commands scopes
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

# Signing secret — used to verify incoming HTTP requests from Slack
# (found in Slack app → Basic Information → App Credentials → Signing Secret)
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")

# ── Thufir API ────────────────────────────────────────────────────────────────
# Base URL of the deployed Thufir Cloud Run service (no trailing slash)
THUFIR_API_URL = os.environ.get("THUFIR_API_URL", "http://localhost:8080")

# Max steps the agent can take per run
THUFIR_MAX_STEPS = int(os.environ.get("THUFIR_MAX_STEPS", "10"))

# Timeout in seconds for waiting on the Thufir API
THUFIR_API_TIMEOUT = int(os.environ.get("THUFIR_API_TIMEOUT", "120"))

