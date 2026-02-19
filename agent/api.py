"""
api.py — FastAPI entrypoint for the Thufir data-retrieval agent.

Deploy to Google Cloud Run as a containerized service.
"""
from __future__ import annotations

import os
import traceback

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.config import DEFAULT_ENDPOINT, DEFAULT_MODEL, DEFAULT_API_KEY
from agent.thufir import run_agent

app = FastAPI(title="Thufir", description="Supabase data-retrieval agent API")


# ── Request / Response models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    prompt: str = Field(..., description="Goal / task for the agent")
    max_steps: int = Field(default=10, ge=1, le=30, description="Max interaction steps")


class RunResponse(BaseModel):
    success: bool
    result: str | None = None
    error: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse)
async def run(req: RunRequest):
    try:
        result = await run_agent(
            prompt=req.prompt,
            endpoint=DEFAULT_ENDPOINT,
            model=DEFAULT_MODEL,
            api_key=DEFAULT_API_KEY,
            max_steps=req.max_steps,
        )

        if result is None:
            return RunResponse(
                success=False,
                error=f"Reached max steps ({req.max_steps}) without an answer.",
            )

        return RunResponse(success=True, result=result)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

