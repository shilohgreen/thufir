# THUFIR

Thufir is a readonly data-retrieval agent that queries a PostgreSQL database
using an OpenAI-compatible LLM.

Ask it a question in natural language and it figures out which tables to query,
writes SQL, and returns a synthesized answer. It never writes data.

Works with any Postgres instance — including Supabase (just use the direct connection string).

## Architecture

```
thufir/
├── agent/               ← Data-retrieval agent (Cloud Run, port 8080)
│   ├── agent.py         — DataAgent: LLM chat loop with retry + JSON parsing
│   ├── api.py           — FastAPI with /health and /run endpoints
│   ├── config.py        — env vars + system prompt
│   ├── postgres_client.py — readonly Postgres client (SQL exec, schema discovery)
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

### Environment variables

Create a `.env` in the project root:

```
# LLM
GEMINI_API_KEY=your-gemini-key

# Postgres (any instance — including Supabase)
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Slack (only needed for the slack bot)
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
THUFIR_API_URL=http://localhost:8080
```

For **Supabase**, grab the connection string from:
Project Settings → Database → Connection string → URI

### Recommended: create a readonly role

```sql
CREATE ROLE thufir_reader WITH LOGIN PASSWORD 'some-password';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO thufir_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO thufir_reader;
```

Then use that role in `DATABASE_URL`. Even if the SQL validation is bypassed, Postgres itself will reject writes.

## Usage

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

### API

```bash
curl -X POST http://localhost:8080/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "How many users signed up this week?"}'
```

## Agent actions

| Action | Description |
|---|---|
| `sql` | Run a readonly `SELECT` query (write statements are blocked at app level + db level) |
| `answer` | Return a final synthesized answer |

Queries are validated before execution — only `SELECT` and `WITH` (CTE) statements are allowed.

## Schema discovery

The agent automatically queries `information_schema.columns` on every run to discover all public tables and columns. No setup or migrations needed.

## Slack commands

| Trigger | Example |
|---|---|
| `/thufir <prompt>` | `/thufir How many active users do we have?` |
| `@thufir <prompt>` | `@thufir Show me the top 5 products by revenue` |
| DM the bot | Just message it directly |
