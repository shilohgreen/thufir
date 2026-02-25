"""
agent/content.py — Content audit module for the Thufir agent.

Cycles through courses → lessons → problems, runs structural checks
and an LLM-based quality review, then returns the report in the response.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

from agent.agent import DataAgent
from agent.config import DEFAULT_ENDPOINT, DEFAULT_MODEL, DEFAULT_API_KEY
from agent.postgres_client import get_pool

logger = logging.getLogger(__name__)

# ── Content audit system prompt ───────────────────────────────────────────────

CONTENT_AUDIT_PROMPT = """\
You are a markdown formatting auditor for a math education platform.

You will receive a lesson and its problems as JSON. Check every text field \
(description, question, explanation, hint_text, options) for markdown issues.

Look for:
- Broken or malformed markdown (unclosed **, `, $$, etc.)
- LaTeX math not wrapped in $ or $$ delimiters
- Raw LaTeX commands outside math delimiters
- Inconsistent formatting (some items bold, others not)
- Broken lists or numbered steps
- Unescaped special characters that break rendering

Respond ONLY with a JSON array. Each issue:
{"problem_title": "...", "field": "...", "issue_type": "...", "description": "...", "suggestion": "..."}

issue_type must be one of: "broken_markdown", "undelimited_latex", \
"inconsistent_formatting", "broken_list", "unescaped_chars"

If no issues are found, respond with: []
Respond ONLY with the JSON array — no markdown, no extra text.
"""


# ── Fetch content ─────────────────────────────────────────────────────────────

async def fetch_content(pool, problem_limit: int = 0) -> dict:
    """Fetch all courses → lessons → problems as a nested structure using JOINs."""

    logger.info("[ 📥 fetch_content ] Querying courses...")
    courses = await pool.fetch("""
        SELECT title, description, is_published, total_lessons,
               estimated_duration_minutes, created_at
        FROM courses ORDER BY created_at
    """)
    logger.info(f"[ 📥 fetch_content ] Fetched {len(courses)} courses")

    logger.info("[ 📥 fetch_content ] Querying lessons...")
    lessons = await pool.fetch("""
        SELECT l.title, l.description, l.order_index,
               l.total_problems, l.estimated_duration_minutes,
               l.lesson_type, l.mastery_session_limit, l.created_at,
               c.title AS course_title
        FROM lessons l
        JOIN courses c ON l.course_id = c.id
        ORDER BY c.created_at, l.order_index
    """)
    logger.info(f"[ 📥 fetch_content ] Fetched {len(lessons)} lessons")

    limit_clause = f"LIMIT {problem_limit}" if problem_limit > 0 else ""
    limit_label = f" (limit: {problem_limit})" if problem_limit > 0 else " (all)"

    logger.info(f"[ 📥 fetch_content ] Querying problems{limit_label}...")
    problems = await pool.fetch(f"""
        SELECT p.title, p.description, p.problem_type,
               p.order_index, p.metadata, p.image_path, p.video_path,
               p.phase, p.misconception, p.question, p.options,
               p.correct_answer, p.explanation, p.points, p.difficulty,
               p.problem_code, p.hint_text,
               ch.filename AS chart_filename,
               ch.chart_type, ch.data AS chart_data,
               l.title AS lesson_title, c.title AS course_title
        FROM problems p
        JOIN lessons l ON p.lesson_id = l.id
        JOIN courses c ON l.course_id = c.id
        LEFT JOIN charts ch ON p.chart_id = ch.id
        ORDER BY c.created_at, l.order_index, p.order_index
        {limit_clause}
    """)
    logger.info(f"[ 📥 fetch_content ] Fetched {len(problems)} problems")

    # Group lessons by course_title
    logger.info("[ 🔗 fetch_content ] Grouping lessons by course...")
    lessons_by_course: dict[str, list[dict]] = {}
    for row in lessons:
        ctitle = row["course_title"]
        lesson = dict(row)
        lesson.pop("course_title", None)
        lessons_by_course.setdefault(ctitle, []).append(lesson)

    for ctitle, llist in lessons_by_course.items():
        logger.info(f"[ 🔗 fetch_content ]   {ctitle}: {len(llist)} lessons")

    # Group problems by (course_title, lesson_title)
    logger.info("[ 🔗 fetch_content ] Grouping problems by lesson...")
    problems_by_lesson: dict[tuple[str, str], list[dict]] = {}
    for row in problems:
        key = (row["course_title"], row["lesson_title"])
        problem = dict(row)
        problem.pop("course_title", None)
        problem.pop("lesson_title", None)
        problems_by_lesson.setdefault(key, []).append(problem)

    charts_found = sum(
        1 for row in problems if row.get("chart_filename") is not None
    )
    logger.info(
        f"[ 🔗 fetch_content ] Grouped into {len(problems_by_lesson)} "
        f"lesson buckets, {charts_found} problems have charts"
    )

    # Assemble nested structure
    content: list[dict] = []
    for c in courses:
        course = dict(c)
        ctitle = course["title"]
        course_lessons = lessons_by_course.get(ctitle, [])
        for lesson in course_lessons:
            ltitle = lesson["title"]
            lesson["problems"] = problems_by_lesson.get((ctitle, ltitle), [])
        course["lessons"] = course_lessons
        content.append(course)

    logger.info("[ ✅ fetch_content ] Content tree assembled")

    return {
        "courses": content,
        "totals": {
            "courses": len(courses),
            "lessons": len(lessons),
            "problems": len(problems),
        },
    }


# ── Structural checks ────────────────────────────────────────────────────────

def structural_checks(content: dict) -> list[dict]:
    """Programmatic checks for missing or inconsistent fields."""
    issues: list[dict] = []
    total_courses = len(content["courses"])

    for ci, course in enumerate(content["courses"], 1):
        ctitle = course["title"]
        lesson_count = len(course.get("lessons", []))
        problem_count = sum(
            len(l.get("problems", [])) for l in course.get("lessons", [])
        )
        logger.info(
            f"[ 🔧 structural_checks ] [{ci}/{total_courses}] "
            f"\"{ctitle}\" — {lesson_count} lessons, {problem_count} problems"
        )

        # ── Course-level ──────────────────────────────────────────────────
        if not course.get("description"):
            issues.append({
                "level": "course", "course": ctitle,
                "issue_type": "missing_field",
                "description": "Course has no description",
            })

        actual_lessons = len(course.get("lessons", []))
        declared_lessons = course.get("total_lessons") or 0
        if actual_lessons != declared_lessons:
            issues.append({
                "level": "course", "course": ctitle,
                "issue_type": "count_mismatch",
                "description": (
                    f"total_lessons={declared_lessons} but actual "
                    f"lesson count is {actual_lessons}"
                ),
            })

        for lesson in course.get("lessons", []):
            ltitle = lesson["title"]

            # ── Lesson-level ──────────────────────────────────────────────
            if not lesson.get("description"):
                issues.append({
                    "level": "lesson", "course": ctitle,
                    "lesson": ltitle,
                    "issue_type": "missing_field",
                    "description": "Lesson has no description",
                })

            actual_problems = len(lesson.get("problems", []))
            declared_problems = lesson.get("total_problems") or 0
            if actual_problems != declared_problems:
                issues.append({
                    "level": "lesson", "course": ctitle,
                    "lesson": ltitle,
                    "issue_type": "count_mismatch",
                    "description": (
                        f"total_problems={declared_problems} but actual "
                        f"problem count is {actual_problems}"
                    ),
                })

            if actual_problems == 0:
                issues.append({
                    "level": "lesson", "course": ctitle,
                    "lesson": ltitle,
                    "issue_type": "empty_lesson",
                    "description": "Lesson has zero problems",
                })

            for problem in lesson.get("problems", []):
                ptitle = problem["title"]
                base = {
                    "level": "problem", "course": ctitle,
                    "lesson": ltitle, "problem": ptitle,
                }

                if not problem.get("explanation"):
                    issues.append({
                        **base, "issue_type": "missing_field",
                        "description": "Problem has no explanation",
                    })

                if not problem.get("question"):
                    issues.append({
                        **base, "issue_type": "missing_field",
                        "description": "Problem has no question text",
                    })

                if problem.get("correct_answer") is None:
                    issues.append({
                        **base, "issue_type": "missing_field",
                        "description": "Problem has no correct_answer",
                    })

                if not problem.get("options"):
                    issues.append({
                        **base, "issue_type": "missing_field",
                        "description": "Problem has no answer options",
                    })

                if not problem.get("difficulty"):
                    issues.append({
                        **base, "issue_type": "missing_field",
                        "description": "Problem has no difficulty level set",
                    })

                if (
                    not problem.get("hint_text")
                    and problem.get("difficulty") in ("medium", "hard")
                ):
                    issues.append({
                        **base, "issue_type": "missing_hint",
                        "description": (
                            f"Problem is '{problem['difficulty']}' but has no hint"
                        ),
                    })

                if not problem.get("misconception"):
                    issues.append({
                        **base, "issue_type": "missing_field",
                        "description": "Problem has no misconception tag",
                    })

                if not problem.get("points"):
                    issues.append({
                        **base, "issue_type": "missing_field",
                        "description": "Problem has no points value",
                    })

    logger.info(
        f"[ ✅ structural_checks ] Done — {len(issues)} issues found"
    )
    return issues


# ── LLM audit ─────────────────────────────────────────────────────────────────

_MARKDOWN_FIELDS = (
    "title", "description", "question", "explanation", "hint_text", "options",
)


async def llm_audit(
    content: dict,
    endpoint: str,
    model: str,
    api_key: str,
    batch_size: int = 10,
) -> list[dict]:
    """Send problems to the LLM in batches for markdown formatting review."""
    issues: list[dict] = []
    audit_start = time.time()

    # Count total batches upfront for progress tracking
    total_problems = 0
    total_batches_all = 0
    for course in content["courses"]:
        for lesson in course.get("lessons", []):
            n = len(lesson.get("problems", []))
            if n > 0:
                total_problems += n
                total_batches_all += (n + batch_size - 1) // batch_size

    logger.info(
        f"[ 🤖 llm_audit ] Starting — {total_problems} problems "
        f"in {total_batches_all} batches (batch_size={batch_size})"
    )

    batch_counter = 0

    for course in content["courses"]:
        ctitle = course["title"]

        for lesson in course.get("lessons", []):
            ltitle = lesson["title"]
            problems = lesson.get("problems", [])

            if not problems:
                continue

            # Only send markdown-relevant fields to keep the payload small
            slim_problems = []
            for p in problems:
                slim = {}
                for field in _MARKDOWN_FIELDS:
                    val = p.get(field)
                    if val is not None:
                        slim[field] = val
                slim_problems.append(slim)

            # Process in batches
            lesson_batches = (len(slim_problems) + batch_size - 1) // batch_size

            for i in range(0, len(slim_problems), batch_size):
                batch = slim_problems[i : i + batch_size]
                batch_num = (i // batch_size) + 1
                batch_counter += 1

                payload = json.dumps(
                    {
                        "course": ctitle,
                        "lesson": ltitle,
                        "problems": batch,
                    },
                    default=str,
                    indent=2,
                )

                logger.info(
                    f"[ 🔍 llm_audit ] [{batch_counter}/{total_batches_all}] "
                    f"{ctitle} / {ltitle} — "
                    f"batch {batch_num}/{lesson_batches} "
                    f"({len(batch)} problems, "
                    f"payload {len(payload)} chars)"
                )

                agent = DataAgent(endpoint, model, api_key)
                batch_start = time.time()

                try:
                    resp = agent.client.chat.completions.create(
                        model=agent.model,
                        messages=[
                            {"role": "system", "content": CONTENT_AUDIT_PROMPT},
                            {
                                "role": "user",
                                "content": f"Review the markdown formatting:\n\n{payload}",
                            },
                        ],
                        temperature=0.2,
                    )
                    reply = resp.choices[0].message.content.strip()
                    batch_elapsed = time.time() - batch_start

                    parsed = _parse_llm_issues(reply)
                    for issue in parsed:
                        issue["course"] = ctitle
                        issue["lesson"] = ltitle
                        issue["source"] = "llm"
                    issues.extend(parsed)

                    logger.info(
                        f"[ ✅ llm_audit ] [{batch_counter}/{total_batches_all}] "
                        f"→ {len(parsed)} issues found ({batch_elapsed:.1f}s)"
                    )

                except Exception as e:
                    batch_elapsed = time.time() - batch_start
                    logger.error(
                        f"[ ❌ llm_audit ] [{batch_counter}/{total_batches_all}] "
                        f"Failed for {ctitle}/{ltitle} "
                        f"batch {batch_num} ({batch_elapsed:.1f}s): {e}"
                    )
                    issues.append({
                        "course": ctitle,
                        "lesson": ltitle,
                        "issue_type": "audit_error",
                        "description": (
                            f"LLM audit failed (batch {batch_num}): {e}"
                        ),
                        "source": "llm",
                    })

    total_elapsed = time.time() - audit_start
    logger.info(
        f"[ ✅ llm_audit ] Complete — {len(issues)} issues found "
        f"across {batch_counter} batches in {total_elapsed:.1f}s"
    )
    return issues


def _parse_llm_issues(text: str) -> list[dict]:
    """Extract a JSON array of issues from the LLM response."""
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return []


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def run_content_audit(
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    api_key: str = DEFAULT_API_KEY,
    skip_llm: bool = False,
    problem_limit: int = 0,
    batch_size: int = 10,
) -> dict:
    """Run the full content audit and return a report."""
    run_start = time.time()
    pool = await get_pool()

    logger.info(
        f"[ 🚀 run_content_audit ] Starting audit "
        f"(problem_limit={problem_limit or 'all'}, "
        f"batch_size={batch_size}, skip_llm={skip_llm})"
    )

    try:
        logger.info("[ 🚀 run_content_audit ] Fetching content...")
        content = await fetch_content(pool, problem_limit=problem_limit)

        logger.info(
            f"[ 📊 run_content_audit ] Found "
            f"{content['totals']['courses']} courses, "
            f"{content['totals']['lessons']} lessons, "
            f"{content['totals']['problems']} problems"
        )

        # ── Pass 1: structural checks ─────────────────────────────────────
        logger.info("[ 🔧 run_content_audit ] Running structural checks...")
        t0 = time.time()
        structural_issues = structural_checks(content)
        logger.info(
            f"[ 🔧 run_content_audit ] Found "
            f"{len(structural_issues)} structural issues "
            f"({time.time() - t0:.1f}s)"
        )

        # ── Pass 2: LLM content review ────────────────────────────────────
        llm_issues: list[dict] = []
        if not skip_llm:
            logger.info("[ 🤖 run_content_audit ] Running LLM markdown review...")
            llm_issues = await llm_audit(
                content, endpoint, model, api_key, batch_size=batch_size,
            )
            logger.info(
                f"[ 🤖 run_content_audit ] Found "
                f"{len(llm_issues)} content issues"
            )
        else:
            logger.info("[ ⏭️ run_content_audit ] Skipping LLM review (skip_llm=True)")

        # ── Build report ──────────────────────────────────────────────────
        total_issues = len(structural_issues) + len(llm_issues)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                **content["totals"],
                "structural_issues": len(structural_issues),
                "content_issues": len(llm_issues),
                "total_issues": total_issues,
            },
            "structural_issues": structural_issues,
            "content_issues": llm_issues,
        }

        total_elapsed = time.time() - run_start
        logger.info(
            f"[ 🏁 run_content_audit ] Audit complete — "
            f"{total_issues} total issues in {total_elapsed:.1f}s"
        )

        return report

    finally:
        await pool.close()

