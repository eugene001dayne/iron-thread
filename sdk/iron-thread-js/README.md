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

// Validate any AI output
const result = await it.validate(
  '{"name": "John", "email": "john@example.com", "age": 28}',
  schema.id
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

// Your AI call
const response = await openai.chat.completions.create({
  model: 'gpt-4',
  messages: [{ role: 'user', content: 'Generate a user profile as JSON' }]
});

const aiOutput = response.choices[0].message.content;

// Validate before touching your database
const result = await it.validate(aiOutput, schemaId, 'gpt-4');

if (result.passed) {
  await db.save(result.data); // safe
} else {
  console.log(`AI output rejected: ${result.reason}`);
}
```

## API

### `new IronThread(host?)`
Initialize the client. Defaults to the hosted API.

### `.createSchema(name, schemaDefinition, description?)`
Create a validation schema. Returns the schema with its `id`.

### `.validate(aiOutput, schemaId, modelUsed?)`
Validate AI output against a schema. Returns a `ValidationResult`.

### `.stats()`
Get dashboard stats — total runs, pass rate, avg latency.

### `.runs()`
Get the last 50 validation runs.

## ValidationResult
```javascript
result.passed      // true or false
result.status      // 'passed' / 'failed' / 'corrected'
result.reason      // why it failed (if it did)
result.data        // the clean validated output
result.latencyMs   // how long validation took
result.runId       // ID of this run in the database
```

## TypeScript Support

iron-thread ships with full TypeScript definitions out of the box.
```typescript
import { IronThread, ValidationResult } from 'iron-thread';

const it = new IronThread();
const result: ValidationResult = await it.validate(aiOutput, schemaId);
```

## Links

- API Docs: https://iron-thread-production.up.railway.app/docs
- GitHub: https://github.com/eugene001dayne/iron-thread
- Python SDK: https://pypi.org/project/iron-thread