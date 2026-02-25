"""
api.py — FastAPI entrypoint for the Thufir data-retrieval agent.

Deploy to Google Cloud Run as a containerized service.
"""
from __future__ import annotations

import traceback

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.config import DEFAULT_ENDPOINT, DEFAULT_MODEL, DEFAULT_API_KEY
from agent.thufir import run_agent
from agent.content import run_content_audit

app = FastAPI(title="Thufir", description="Readonly data-retrieval agent API")


# ── Request / Response models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    prompt: str = Field(..., description="Goal / task for the agent")
    max_steps: int = Field(default=10, ge=1, le=30, description="Max interaction steps")


class RunResponse(BaseModel):
    success: bool
    result: str | None = None
    error: str | None = None


class AuditRequest(BaseModel):
    skip_llm: bool = Field(
        default=False,
        description="Skip LLM review — only run structural checks (much faster)",
    )
    problem_limit: int = Field(
        default=0, ge=0,
        description="Max problems to fetch (0 = all)",
    )
    batch_size: int = Field(
        default=10, ge=1, le=50,
        description="Problems per LLM batch",
    )


class AuditResponse(BaseModel):
    success: bool
    report: dict | None = None
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


@app.post("/audit", response_model=AuditResponse)
async def audit(req: AuditRequest = AuditRequest()):
    """Run a content audit across all courses, lessons, and problems."""
    try:
        report = await run_content_audit(
            endpoint=DEFAULT_ENDPOINT,
            model=DEFAULT_MODEL,
            api_key=DEFAULT_API_KEY,
            skip_llm=req.skip_llm,
            problem_limit=req.problem_limit,
            batch_size=req.batch_size,
        )

        return AuditResponse(success=True, report=report)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
