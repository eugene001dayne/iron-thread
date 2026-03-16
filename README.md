# Iron-Thread ⚡

> The ruthless middleware that stops broken AI outputs from reaching your database.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)

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
git clone https://github.com/eugene001dayne/iron-thread.git
cd iron-thread
pip install -r requirements.txt
cp .env.example .env  # add your keys
python -m uvicorn main:app --reload
```

Open `http://localhost:8000/docs` to see the full API.

## How It Works

**1. Define your schema**
```json
POST /schemas
{
  "name": "User Profile",
  "schema_definition": {
    "required": ["name", "email", "age"],
    "properties": {
      "name": {"type": "string"},
      "email": {"type": "string"},
      "age": {"type": "integer"}
    }
  }
}
```

**2. Validate any AI output**
```json
POST /validate
{
  "schema_id": "your-schema-id",
  "ai_output": "{\"name\": \"John\", \"email\": \"john@example.com\"}",
  "model_used": "gpt-4"
}
```

**3. Get instant verdict**
```json
{
  "status": "failed",
  "reason": "Missing required field: age",
  "validated_output": null,
  "latency_ms": 12
}
```

## Features

- ✅ JSON schema validation with clear error reasons
- ✅ Every run logged with latency and model tracking
- ✅ Live dashboard with pass/fail/corrected stats
- ✅ REST API — works with any language or framework
- ✅ Supabase backend — no setup, just connect
- 🔜 AI auto-correction loop (coming soon)
- 🔜 Webhook alerts on failure
- 🔜 SDK for Python and JavaScript

## Live Demo

API: `https://iron-thread-production.up.railway.app`  
Docs: `https://iron-thread-production.up.railway.app/docs`

## Stack

- **Backend:** FastAPI + Python
- **Database:** Supabase (PostgreSQL)
- **Dashboard:** React (Lovable)
- **Deployment:** Railway

## Contributing

PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — free to use, modify, and distribute.

---

Built for the age of AI agents. Star ⭐ if Iron-Thread saves you from dirty data.