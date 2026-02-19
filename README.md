# THUFIR

Thufir is a readonly data-retrieval agent that queries a Supabase database
using an OpenAI-compatible LLM.

Ask it a question in natural language and it figures out which tables to query,
applies filters, and returns a synthesized answer. It never writes data.

## Architecture

```
thufir/
├── agent/               ← Supabase data-retrieval agent (Cloud Run, port 8080)
│   ├── agent.py         — DataAgent: LLM chat loop with retry + JSON parsing
│   ├── api.py           — FastAPI with /health and /run endpoints
│   ├── config.py        — env vars + system prompt
│   ├── supabase_client.py — readonly Supabase client (query, rpc, schema)
│   └── thufir.py        — CLI entrypoint + agent loop
├── slack/               ← Slack bot (Cloud Run, port 3000)
│   ├── app.py           — Bolt + FastAPI (HTTP mode)
│   ├── client.py        — async HTTP client calling Thufir /run
│   ├── config.py        — Slack + Thufir API env vars
│   ├── handlers.py      — /thufir command, @thufir mention, DMs
│   └── verify_setup.py  — token/scope checker
├── Dockerfile           — agent container
└── Dockerfile.slack     — slack bot container
```

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- A Supabase project with an `anon` or `service_role` key
- (Optional) A `get_schema_info` RPC function in Supabase so the agent can discover tables

### Install dependencies

**Agent:**

```bash
cd agent
uv sync
```

**Slack bot:**

```bash
cd slack
uv sync
```

### Environment variables

Create a `.env` in the project root:

```
# LLM
GEMINI_API_KEY=your-gemini-key

# Supabase (readonly)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...

# Slack (only needed for the slack bot)
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
THUFIR_API_URL=http://localhost:8080
```

## Usage

### CLI

```bash
cd agent
uv run python -m agent.thufir --prompt "How many users signed up this week?"
```

### API server (local)

```bash
cd agent
uv run uvicorn agent.api:app --host 0.0.0.0 --port 8080
```

Then call it:

```bash
curl -X POST http://localhost:8080/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "How many users signed up this week?"}'
```

### Slack bot (local)

```bash
cd slack
uv run uvicorn slack.app:fastapi_app --host 0.0.0.0 --port 3000
```

### Docker

**Agent:**

```bash
docker build -f Dockerfile -t thufir-agent .
docker run -p 8080:8080 --env-file .env thufir-agent
```

**Slack bot:**

```bash
docker build -f Dockerfile.slack -t thufir-slack .
docker run -p 3000:3000 --env-file .env thufir-slack
```

## Agent actions

The LLM can perform three actions per turn:

| Action | Description |
|---|---|
| `query` | SELECT from a table with optional filters (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `like`, `ilike`, `in`, `is`) and a limit |
| `rpc` | Call a readonly Supabase RPC function with params |
| `answer` | Return a final synthesized answer to the user |

## Slack commands

| Trigger | Example |
|---|---|
| `/thufir <prompt>` | `/thufir How many active users do we have?` |
| `@thufir <prompt>` | `@thufir Show me the top 5 products by revenue` |
| DM the bot | Just message it directly |

## Supabase schema discovery

The agent calls a `get_schema_info` RPC on startup to learn what tables and columns
are available. Create it in Supabase SQL editor:

```sql
create or replace function get_schema_info()
returns json
language sql
security definer
as $$
  select json_agg(row_to_json(t))
  from (
    select
      table_name,
      json_agg(json_build_object(
        'column', column_name,
        'type', data_type
      )) as columns
    from information_schema.columns
    where table_schema = 'public'
    group by table_name
    order by table_name
  ) t;
$$;
```

If this RPC doesn't exist, the agent will still work — it just won't auto-discover
the schema and you'll need to tell it which tables to query in your prompt.
