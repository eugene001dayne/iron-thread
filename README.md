# Iron-Thread ⚡

> The ruthless middleware that stops broken AI outputs from reaching your database — and tells you exactly why they keep failing.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![npm](https://img.shields.io/badge/npm-iron--thread-red.svg)](https://www.npmjs.com/package/iron-thread)
[![PyPI](https://img.shields.io/badge/pypi-iron--thread-blue.svg)](https://pypi.org/project/iron-thread)
[![Version](https://img.shields.io/badge/version-0.2.0-green.svg)](https://github.com/eugene001dayne/iron-thread)

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
            "name": {"type": "string", "minLength": 2},
            "email": {"type": "string"},
            "age": {"type": "integer", "minimum": 18, "maximum": 100}
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
results = it.validate_batch(
    ai_outputs=["output1", "output2", "output3"],
    schema_id=schema["id"],
    model_used="gpt-4"
)

print(f"{results.passed}/{results.total} passed ({results.success_rate}%)")

for r in results.results:
    if not r.passed:
        print(f"Failed: {r.reason}")
```

## Webhook Alerts

Get notified instantly when validation fails:
```python
it.create_webhook(
    name="Slack Alert",
    url="https://hooks.slack.com/your-webhook",
    on_failure=True,
    on_success=False
)
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

## Advanced Validation Types
```json
{
  "properties": {
    "username": {
      "type": "string",
      "minLength": 3,
      "maxLength": 20
    },
    "age": {
      "type": "integer",
      "minimum": 18,
      "maximum": 100
    },
    "role": {
      "type": "string",
      "enum": ["admin", "user", "moderator"]
    },
    "email": {
      "type": "string",
      "pattern": "^[\\w.-]+@[\\w.-]+\\.\\w+$"
    },
    "tags": {
      "type": "array",
      "minItems": 1,
      "maxItems": 5
    }
  }
}
```

## Analytics
```python
# Error patterns — why does my AI keep failing?
it.analytics_errors()

# Trends over time — is my agent getting better?
it.analytics_trends()

# Which model performs best?
it.analytics_models()

# Which schemas fail most?
it.analytics_schemas()

# Export all runs as CSV
it.export_csv("runs.csv")
```

## Health Check
```python
it.health()
# {"status": "healthy", "database": "healthy", "db_latency_ms": 45}
```

## Features

- ✅ Single and batch JSON schema validation
- ✅ Advanced types — enum, regex, range, length, array size
- ✅ Every run logged with latency and model tracking
- ✅ Live dashboard with real-time stats
- ✅ Pattern analytics — why does my AI keep failing?
- ✅ Trends over time — is my agent improving?
- ✅ Model performance comparison
- ✅ Schema performance tracking
- ✅ Webhook alerts on failure or success
- ✅ CSV export for compliance and auditing
- ✅ Health check endpoint
- ✅ Rate limiting
- ✅ Python SDK + JavaScript SDK
- 🔜 AI auto-correction loop
- 🔜 Per-user API keys
- 🔜 Multi-tenancy

## All Endpoints
```
GET    /                         → status check
GET    /health                   → health + db latency
POST   /schemas                  → create validation schema
GET    /schemas                  → list all schemas
POST   /validate                 → validate single AI output
POST   /validate/batch           → validate multiple outputs
GET    /dashboard/stats          → overview stats
GET    /runs                     → recent validation runs
GET    /runs/export              → download runs as CSV
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

## Self-Hosting
```bash
git clone https://github.com/eugene001dayne/iron-thread.git
cd iron-thread
pip install -r requirements.txt
cp .env.example .env
# Add your Supabase credentials
python -m uvicorn main:app --reload
```

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
