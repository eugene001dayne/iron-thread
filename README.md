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
                        → ❌ Blocked + Logged → Auto-Correction
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

# Validate any AI output
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

## Features

- ✅ JSON schema validation with clear error reasons
- ✅ Every run logged with latency and model tracking
- ✅ Live dashboard with real-time stats
- ✅ Pattern analytics — why does my AI keep failing?
- ✅ Trends over time — is my agent getting better or worse?
- ✅ Model performance comparison — which model produces cleaner output?
- ✅ Schema performance tracking — which schemas fail most?
- ✅ REST API — works with any language or framework
- ✅ Python SDK + JavaScript SDK
- 🔜 AI auto-correction loop
- 🔜 Webhook alerts on failure
- 🔜 Per-user API keys and multi-tenancy

## API Endpoints
```
GET  /                    → status check
POST /schemas             → create validation schema
GET  /schemas             → list all schemas
POST /validate            → validate AI output
GET  /dashboard/stats     → overview stats
GET  /runs                → recent validation runs
GET  /analytics/errors    → most common failure patterns
GET  /analytics/trends    → success rate over time
GET  /analytics/models    → performance by AI model
GET  /analytics/schemas   → performance by schema
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