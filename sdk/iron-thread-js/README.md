# iron-thread

> Ruthless middleware that stops broken AI outputs from reaching your database.

## Install
```bash
npm install iron-thread
```

## Quick Start
```javascript
const { IronThread } = require('iron-thread');

const it = new IronThread();

// Create a schema
const schema = await it.createSchema(
  'User Profile',
  {
    required: ['name', 'email', 'age'],
    properties: {
      name: { type: 'string' },
      email: { type: 'string' },
      age: { type: 'integer' }
    }
  }
);

// Validate any AI output (autoCorrect optional)
const result = await it.validate(
  '{"name": "John", "email": "john@example.com", "age": 28}',
  schema.id,
  'gpt-4',
  true   // enable auto-correction
);

if (result.passed) {
  console.log('Clean — safe to send to database');
  console.log(result.data);
} else {
  console.log(`Blocked — ${result.reason}`);
}
```

## Real World Usage with OpenAI
```javascript
const OpenAI = require('openai');
const { IronThread } = require('iron-thread');

const openai = new OpenAI();
const it = new IronThread();

const response = await openai.chat.completions.create({
  model: 'gpt-4',
  messages: [{ role: 'user', content: 'Generate a user profile as JSON' }]
});

const aiOutput = response.choices[0].message.content;

// Validate before touching your database
const result = await it.validate(aiOutput, schemaId, 'gpt-4', true);

if (result.passed) {
  await db.save(result.data);
} else {
  console.log(`AI output rejected: ${result.reason}`);
}
```

## API

### `new IronThread(host?)`
Initialize the client. Defaults to `https://iron-thread.onrender.com`.

### `.createSchema(name, schemaDefinition, description?)`
Create a validation schema. Returns the schema with its `id`.

### `.validate(aiOutput, schemaId, modelUsed?, autoCorrect?)`
Validate AI output against a schema. Returns a `ValidationResult`.  
Set `autoCorrect` to `true` to attempt fixing common JSON errors.

### `.validateBatch(aiOutputs, schemaId, modelUsed?)`
Validate multiple outputs at once. Returns a `BatchValidationResult`.

### `.verifyRun(runId)`
Check the tamper‑evident hash of a validation run.

### `.getSchemaChain(schemaId)`
Get the full hash chain for a schema.

### `.stats()`
Get dashboard stats — total runs, pass rate, avg latency.

### `.runs()`
Get the last 50 validation runs.

## ValidationResult (v0.3.0)
```javascript
result.passed           // true or false
result.status           // 'passed' / 'failed' / 'corrected'
result.reason           // why it failed (if it did)
result.data             // the clean validated output
result.auto_corrected   // whether auto-correction was applied
result.confidence_score // 0–1 confidence in the result
result.confidence_flags // array of warnings (e.g., ['low_confidence'])
result.attempts         // number of correction attempts
result.latencyMs        // how long validation took
result.runId            // ID of this run in the database
```

## TypeScript Support

TypeScript definitions are not yet available for v0.3.0. Check back soon.

## Links

- API Docs: https://iron-thread.onrender.com/docs
- GitHub: https://github.com/eugene001dayne/iron-thread
- Python SDK: https://pypi.org/project/iron-thread