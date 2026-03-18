# Iron-Thread ⚡

> The ruthless middleware that stops broken AI outputs from reaching your database — and tells you exactly why they keep failing.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![npm](https://img.shields.io/badge/npm-iron--thread-red.svg)](https://www.npmjs.com/package/iron-thread)
[![PyPI](https://img.shields.io/badge/pypi-iron--thread-blue.svg)](https://pypi.org/project/iron-thread)

## The Problem

You're chaining AI agents to your database. It's working great — until the AI returns:

- Conversational text instead of JSON
- Missing required fields
- Wrong data types
- Hallucinated values

Your automation crashes. Your database gets dirty data. You waste hours debugging.

## The Solution

Iron-Thread sits between your AI model and your database as a ruthless checkpoint:
```
AI Output → Iron-Thread → ✅ Clean Data → Your Database
                        → ❌ Blocked + Logged → Webhook Alert
```

## Quick Start
```bash
pip install iron-thread
```
```python
from ironthread import IronThread

it = IronThread()

# Create a schema
schema = it.create_schema(
    name="User Profile",
    schema_definition={
        "required": ["name", "email", "age"],
        "properties": {
            "name": {"type": "string"},
            "email": {"type": "string"},
            "age": {"type": "integer"}
        }
    }
)

# Validate single output
result = it.validate(
    ai_output='{"name": "John", "email": "john@example.com", "age": 28}',
    schema_id=schema["id"]
)

if result.passed:
    print("Clean — safe to send to database")
else:
    print(f"Blocked — {result.reason}")
```

## JavaScript / Node.js
```bash
npm install iron-thread
```
```javascript
const { IronThread } = require('iron-thread');
const it = new IronThread();

const result = await it.validate(aiOutput, schemaId, 'gpt-4');

if (result.passed) {
  await db.save(result.data);
} else {
  console.log(`Rejected: ${result.reason}`);
}
```

## Batch Validation

Validate multiple AI outputs in one call:
```python
# Coming in SDK v0.2.0
# Use the API directly for now
POST /validate/batch
{
  "schema_id": "your-schema-id",
  "ai_outputs": ["output1", "output2", "output3"],
  "model_used": "gpt-4"
}
```

Response:
```json
{
  "total": 3,
  "passed": 2,
  "failed": 1,
  "success_rate": 66.67,
  "results": [...]
}
```

## Webhook Alerts

Get notified instantly when validation fails:
```python
POST /webhooks
{
  "name": "Slack Alert",
  "url": "https://hooks.slack.com/your-webhook",
  "on_failure": true,
  "on_success": false
}
```

Iron-Thread fires a POST to your URL with:
```json
{
  "event": "validation.failed",
  "schema_id": "...",
  "run": {
    "run_id": "...",
    "status": "failed",
    "reason": "Missing required field: email",
    "model_used": "gpt-4",
    "latency_ms": 234
  },
  "timestamp": 1234567890
}
```

Connect to Slack, Discord, PagerDuty, or any URL.

## Features

- ✅ Single and batch JSON schema validation
- ✅ Every run logged with latency and model tracking
- ✅ Live dashboard with real-time stats
- ✅ Pattern analytics — why does my AI keep failing?
- ✅ Trends over time — is my agent getting better or worse?
- ✅ Model performance comparison
- ✅ Schema performance tracking
- ✅ Webhook alerts on failure or success
- ✅ Python SDK + JavaScript SDK
- 🔜 AI auto-correction loop
- 🔜 More validation types (regex, enum, range)
- 🔜 Export runs as CSV
- 🔜 Per-user API keys

## API Endpoints
```
GET    /                         → status check
POST   /schemas                  → create validation schema
GET    /schemas                  → list all schemas
POST   /validate                 → validate single AI output
POST   /validate/batch           → validate multiple outputs
GET    /dashboard/stats          → overview stats
GET    /runs                     → recent validation runs
GET    /analytics/errors         → most common failure patterns
GET    /analytics/trends         → success rate over time
GET    /analytics/models         → performance by AI model
GET    /analytics/schemas        → performance by schema
POST   /webhooks                 → create webhook alert
GET    /webhooks                 → list webhooks
DELETE /webhooks/{id}            → delete webhook
```

## Live Demo

- API: `https://iron-thread-production.up.railway.app`
- Docs: `https://iron-thread-production.up.railway.app/docs`

## Stack

- **Backend:** FastAPI + Python
- **Database:** Supabase (PostgreSQL)
- **Dashboard:** React (Lovable)
- **Deployment:** Railway

## The Thread Suite

Part of the Thread Suite — Iron-Thread · Test-Thread · Prompt-Thread

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — free to use, modify, and distribute.

---

Built for the age of AI agents.
Star ⭐ if Iron-Thread saves you from dirty data.