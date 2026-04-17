# iron-thread

> Open‑source middleware that validates AI outputs before they reach your database.

## Install
```bash
pip install iron-thread
```

## Quick Start
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

# Validate any AI output (auto_correct enabled)
result = it.validate(
    ai_output='{"name": "John", "email": "john@example.com", "age": 28}',
    schema_id=schema["id"],
    auto_correct=True
)

if result.passed:
    print("Clean — safe to send to database")
    print(result.data)
    print(f"Confidence: {result.confidence_score}")
else:
    print(f"Blocked — {result.reason}")
```

## Real World Usage
```python
import openai
from ironthread import IronThread

it = IronThread()
client = openai.OpenAI()

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Generate a user profile as JSON"}]
)

ai_output = response.choices[0].message.content

# Validate before touching your database
result = it.validate(
    ai_output=ai_output,
    schema_id="your-schema-id",
    model_used="gpt-4",
    auto_correct=True
)

if result.passed:
    db.save(result.data)  # safe
else:
    print(f"AI output rejected: {result.reason}")
```

## API

### `IronThread(host=None)`
Initialize the client. Defaults to `https://iron-thread.onrender.com`.

### `.create_schema(name, schema_definition, description="")`
Create a validation schema. Returns the schema with its `id`.

### `.validate(ai_output, schema_id, model_used=None, auto_correct=False)`
Validate AI output against a schema. Returns a `ValidationResult`.  
Set `auto_correct=True` to automatically fix common JSON errors.

### `.validate_batch(ai_outputs, schema_id, model_used=None)`
Validate multiple outputs at once. Returns a `BatchValidationResult`.

### `.verify_run(run_id)`
Check the tamper‑evident hash of a validation run.

### `.get_schema_chain(schema_id)`
Get the full hash chain for a schema (audit trail).

### `.stats()`
Get dashboard stats — total runs, pass rate, avg latency.

### `.runs()`
Get the last 50 validation runs.

## ValidationResult (v0.3.0)
```python
result.passed             # True or False
result.status             # "passed" / "failed" / "corrected"
result.reason             # why it failed (if it did)
result.data               # the clean validated output
result.auto_corrected     # whether auto‑correction was applied
result.attempts           # number of correction attempts
result.confidence_score   # 0–1 confidence in the result
result.confidence_flags   # list of warnings (e.g., ['low_confidence'])
result.latency_ms         # how long validation took
result.run_id             # ID of this run in the database
```

## BatchValidationResult
```python
batch.total          # total inputs
batch.passed         # count passed
batch.failed         # count failed
batch.corrected      # count auto‑corrected
batch.success_rate   # percentage passed (0‑100)
batch.results        # list of ValidationResult objects
```

## Links

- API Docs: https://iron-thread.onrender.com/docs
- GitHub: https://github.com/eugene001dayne/iron-thread
- JavaScript SDK: https://www.npmjs.com/package/iron-thread