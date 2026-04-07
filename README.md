# Iron-Thread

The middleware that stops broken AI outputs from hitting your database — and tells you why they keep failing.

You're hooking AI agents straight to your database. Works fine until the AI decides to send you a paragraph of chit-chat instead of JSON, forgets a required field, makes up a number, or hands you a string when you asked for an integer.

Then your automation crashes, your database ends up with garbage, and you lose an hour debugging.

Iron-Thread sits between your AI model and your database. It checks every output against a schema. Good data passes through. Bad data gets blocked, logged, and can trigger a webhook.

## Quick start

```bash
pip install iron-thread
```

```python
from ironthread import IronThread

it = IronThread()

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

result = it.validate(
    ai_output='{"name": "John", "email": "john@example.com", "age": 28}',
    schema_id=schema["id"]
)

if result.passed:
    print("Clean — safe to send to database")
else:
    print(f"Blocked — {result.reason}")
```

Same thing works in Node.js:

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

## Batch validation

Validate multiple outputs in one call:

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

## Webhook alerts

Get notified the moment validation fails:

```python
it.create_webhook(
    name="Slack Alert",
    url="https://hooks.slack.com/your-webhook",
    on_failure=True,
    on_success=False
)
```

Iron-Thread sends a POST to your URL with a payload like this:

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

Hook it up to Slack, Discord, PagerDuty — anything that accepts webhooks.

## Advanced validation

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
# Most common failure reasons
it.analytics_errors()

# Success rate over time
it.analytics_trends()

# Which model performs best?
it.analytics_models()

# Which schemas fail the most?
it.analytics_schemas()

# Export everything as CSV
it.export_csv("runs.csv")
```

## Health check

```python
it.health()
# {"status": "healthy", "database": "healthy", "db_latency_ms": 45}
```

## What it does

- Single and batch JSON schema validation
- Advanced types — enum, regex, range, length, array size
- Logs every run with latency and model name
- Live dashboard with real-time stats
- Pattern analytics — why does your AI keep failing?
- Trends over time — is your agent improving?
- Model performance comparison
- Schema performance tracking
- Webhook alerts on failure or success
- CSV export for compliance and auditing
- Health check endpoint
- Rate limiting
- Python SDK + JavaScript SDK
- Coming later: AI auto-correction loop, per-user API keys, multi-tenancy

## API endpoints

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

## Live demo

- API: `https://iron-thread-production.up.railway.app`
- Docs: `https://iron-thread-production.up.railway.app/docs`
- Dashboard: `https://iron-thread-dashboard.lovable.app`

## Self-hosting

```bash
git clone https://github.com/eugene001dayne/iron-thread.git
cd iron-thread
pip install -r requirements.txt
cp .env.example .env
# Add your Supabase credentials
python -m uvicorn main:app --reload
```

## Stack

- Backend: FastAPI + Python
- Database: Supabase (PostgreSQL)
- Dashboard: React (Lovable)
- Deployment: Railway

## Part of the Thread Suite

Iron-Thread · Test-Thread · Prompt-Thread .Chain-Thread

## Contributing

Pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — use it, break it, fix it, ship it.

---

Built for the age of AI agents. Star this repo if it saves you from dirty data.
