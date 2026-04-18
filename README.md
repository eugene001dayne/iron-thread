# Iron-Thread

**Open-source middleware that validates AI outputs before they reach your database.**

[![PyPI version](https://badge.fury.io/py/iron-thread.svg)](https://pypi.org/project/iron-thread/)
[![npm version](https://badge.fury.io/js/iron-thread.svg)](https://www.npmjs.com/package/iron-thread)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Part of Thread Suite](https://img.shields.io/badge/Thread%20Suite-Iron--Thread-black)](https://github.com/eugene001dayne)

---

## The problem

When you chain an AI model to a database, the AI eventually returns broken output. Wrong types. Missing fields. Hallucinated values that look plausible but aren't valid. Your automation crashes. Your database gets dirty data. You find out when something downstream breaks — not before.

There was no clean, lightweight, open-source checkpoint for this. Iron-Thread is that checkpoint.

```
AI Output → Iron-Thread → ✅ Clean Data → Database
                        → ❌ Blocked + Logged → Auto-Correction → Retry
```

---

## What it does

- **Validates** AI output against a JSON schema before it touches your database
- **Blocks** outputs that fail — wrong types, missing fields, out-of-range values, bad patterns
- **Auto-corrects** failed outputs using Google Gemini and retries validation
- **Scores** content reliability — flags statistically anomalous values that pass schema but look wrong
- **Chains** every run into a tamper-evident SHA-256 audit trail
- **Logs** everything — every run, every correction, every failure
- **Alerts** via webhooks when validation fails
- **Analyzes** failure patterns, trends, and performance by model and schema

---

## Install

**Python**
```bash
pip install iron-thread
```

**JavaScript**
```bash
npm install iron-thread
```

---

## Quickstart

**Python**
```python
from ironthread import IronThread

it = IronThread()  # points to https://iron-thread.onrender.com

# Define your schema
schema = it.create_schema("User Profile", {
    "required": ["name", "email", "age"],
    "properties": {
        "name": {"type": "string", "minLength": 2},
        "email": {"type": "string"},
        "age": {"type": "integer", "minimum": 18, "maximum": 100},
        "role": {"type": "string", "enum": ["admin", "user"]}
    }
})

# Validate AI output
result = it.validate(ai_output, schema["id"], model_used="gpt-4")

print(result.status)           # "passed", "failed", or "corrected"
print(result.confidence_score) # 0.0–1.0 — how reliable the content looks
print(result.confidence_flags) # fields that look statistically anomalous
```

**Auto-correction**
```python
result = it.validate(ai_output, schema["id"], auto_correct=True)

print(result.auto_corrected)  # True if Gemini fixed it
print(result.attempts)        # 1 or 2
```

**Batch validation**
```python
batch = it.validate_batch(["output1", "output2", "output3"], schema["id"])

print(batch.success_rate)  # e.g. 66.67
print(batch.failed)        # 1
```

**JavaScript**
```javascript
const { IronThread } = require('iron-thread');
const it = new IronThread();

const result = await it.validate(aiOutput, schemaId, 'gpt-4');
console.log(result.status);
console.log(result.confidence_score);
```

---

## Validation types

| Constraint | Property | Example |
|-----------|----------|---------|
| Required fields | `"required": [...]` | `"required": ["name", "email"]` |
| String | `"type": "string"` | any string |
| Integer | `"type": "integer"` | whole numbers only |
| Number | `"type": "number"` | int or float |
| Boolean | `"type": "boolean"` | true/false |
| Array | `"type": "array"` | list |
| Object | `"type": "object"` | nested object |
| Min length | `"minLength": 3` | string at least 3 chars |
| Max length | `"maxLength": 100` | string at most 100 chars |
| Minimum value | `"minimum": 18` | number >= 18 |
| Maximum value | `"maximum": 100` | number <= 100 |
| Enum | `"enum": ["a","b","c"]` | value must be one of these |
| Pattern | `"pattern": "^[a-z]+$"` | must match regex |
| Min items | `"minItems": 1` | array >= 1 items |
| Max items | `"maxItems": 5` | array <= 5 items |

---

## Confidence scoring

Iron-Thread doesn't just check structure — it scores content reliability. After a run passes validation, a second pass compares values against the statistical history of past runs for that schema.

- **Numeric fields** — flags values beyond 3 standard deviations from the historical mean
- **String fields** — flags lengths beyond 3 standard deviations from historical mean length
- **Enum fields** — flags values that have never appeared before in past runs

Returns `confidence_score` (0.0–1.0) and `confidence_flags` (list of anomalous fields). Activates automatically after 10 passing runs. No AI needed — fully deterministic.

```python
result = it.validate(ai_output, schema["id"])

if result.confidence_score < 0.8:
    print("Anomalous fields:", result.confidence_flags)
    # flag for human review
```

---

## Tamper-evident audit trail

Every validation run is hashed with SHA-256 at write time. Each hash incorporates the previous run's hash, creating a verifiable chain. Any tampering with any historical run breaks all subsequent links.

```python
# Verify a single run
verify = it.verify_run(result.run_id)
print(verify["verified"])  # True or False

# Verify the full chain for a schema
chain = it.get_schema_chain(schema["id"])
print(chain["chain_verified"])  # True or False
```

Hand the chain endpoint response to a regulator. The math speaks for itself.

---

## Webhooks

```python
it.create_webhook(
    name="Slack alert",
    url="https://hooks.slack.com/your-webhook",
    on_failure=True,
    on_success=False
)
```

Fires a POST with run details whenever validation fails.

---

## Analytics

```python
it.stats()              # overview — totals, success rate, avg confidence
it.analytics_errors()   # failure patterns by schema
it.analytics_trends()   # success rate over time
it.analytics_models()   # performance by AI model
it.analytics_schemas()  # performance by schema
it.export_csv()         # download full run history
```

---

## Self-hosted API

The Iron-Thread API is open source. Deploy your own instance:

```bash
git clone https://github.com/eugene001dayne/iron-thread
cd iron-thread
pip install -r requirements.txt

# Set environment variables
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
GOOGLE_API_KEY=your_key  # for auto-correction

python -m uvicorn main:app --reload
```

Live hosted API: `https://iron-thread.onrender.com`
API docs: `https://iron-thread.onrender.com/docs`

---

## Part of the Thread Suite

Iron-Thread is one of five open-source tools in the Thread Suite — the reliability layer for AI agents.

| Tool | What it does |
|------|-------------|
| **Iron-Thread** | Validates AI output structure before your database |
| **TestThread** | Tests whether your agent behaves correctly |
| **PromptThread** | Versions prompts and tracks performance over time |
| **ChainThread** | Verifies and governs agent-to-agent handoffs |
| **PolicyThread** | Monitors production AI against compliance rules |

---

## License

Apache 2.0 — free to use, modify, and distribute.

---

*Built by [Eugene Dayne Mawuli](https://github.com/eugene001dayne)*
*"Built for the age of AI agents."*