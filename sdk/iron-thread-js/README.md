# iron-thread: JavaScript client

The JavaScript client for [Iron-Thread](https://github.com/eugene001dayne/iron-thread): check AI output against a
JSON Schema before it reaches your database, and verify the signed receipt every verdict comes with.

You need an Iron-Thread server. It runs on your own machine in about a minute; see the
[main README](https://github.com/eugene001dayne/iron-thread#quickstart-about-a-minute).

## Install

```bash
npm install iron-thread
```

Node 20 or newer. No dependencies (it uses the built-in `fetch` and `crypto`). TypeScript types are included.
Version 0.4 works with Iron-Thread server 2.x. Earlier releases of this package pointed at a hosted service that
no longer exists.

## Quickstart

```js
const { IronThread } = require("iron-thread");       // or: import { IronThread } from "iron-thread";

const it = new IronThread();                          // http://localhost:8000, or $IRONTHREAD_URL

const schema = await it.createSchema("invoice", {
  type: "object",
  required: ["customer", "amount"],
  properties: { customer: { type: "string" }, amount: { type: "number", minimum: 0 } },
});

const ok = await it.validate({ customer: "Acme Ltd", amount: 120.5 }, schema.id);   // objects are serialised for you
console.log(ok.status, ok.reason);                    // passed  Validation passed

const bad = await it.validate('{"customer": "Acme Ltd", "amount": "about 120"}', schema.id);
console.log(bad.status, bad.reason);                  // failed  Field 'amount' must be a number, got str
```

Results use the server's field names (`run_id`, `latency_ms`, `confidence_score`, `attestation`).

## The signed receipt

Every result carries `attestation`: an Ed25519-signed, hash-chained record of the input, the output, the exact
schema and the verdict. It holds hashes, not your data.

```js
const publicKey = "...";   // get it from a source you trust, for example pinned in your own repository

const check = await it.verifyChainOffline(schema.id, publicKey, { expectHead: recordedHeadHash });
if (!check.ok) throw new Error(check.message);       // "entry 2: contents were altered after signing", ...
```

`verifyChainOffline` downloads the chain and checks it **on your machine**. Prefer a public key you did not fetch
from the same server, and pass `expectHead` / `expectLength` that you recorded earlier: that is what catches a
chain whose newest entries were deleted.

The check is also available as a plain function, with no client or network involved:

```js
const { verifyChain } = require("iron-thread");       // or require("iron-thread/verify")
const { ok, message } = verifyChain(entries, publicKey, { expectHead });
```

It reproduces the server's canonical JSON byte for byte, and the test suite proves that against receipts signed
by the Python server. The one known difference is floating-point formatting (`1.0` versus `1`); receipt bodies
contain no floats, so verification is unaffected.

| Method | What it does |
|---|---|
| `getAttestation(runId)` | One run's receipt |
| `getChain(schemaId)` | Every receipt for a schema, oldest first |
| `verifyChainOffline(schemaId, publicKey, options)` | Check a chain yourself, locally |
| `verifyChainRemote(schemaId)` | Ask the server (you are trusting its answer) |
| `verifyAttestation(entry, { input, output, schemaDefinition })` | Check one receipt against your data |
| `reconcile(schemaId)` | Do the stored runs still match what was signed? |
| `publicKeys()` | The server's public signing keys |

## API keys

A server in its default mode only accepts requests from its own machine. If it uses API keys:

```js
const it = new IronThread("https://your-server", { apiKey: "it_..." });   // or set $IRONTHREAD_API_KEY
```

## Errors

Server errors reject with `IronThreadError`, which has `.status` and the server's own explanation in `.detail`.
`status` is `0` if the server could not be reached at all, and the message says how to start it.

## Other methods

`listSchemas`, `validateBatch`, `runs`, `exportRuns`, `stats`, `analyticsErrors`, `analyticsTrends`,
`analyticsModels`, `analyticsSchemas`, `createWebhook`, `listWebhooks`, `deleteWebhook`, `health`.
`verifyRun` and `getSchemaChain` use the older unsigned hash chain; prefer the receipts.

Apache 2.0. Part of the [Thread Suite](https://github.com/eugene001dayne).
