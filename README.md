# Iron-Thread

**Check AI output before it reaches your database, and keep a signed receipt anyone can verify.**
**Learn more at: threadsuite.netlify.app**

[![PyPI version](https://badge.fury.io/py/iron-thread.svg)](https://pypi.org/project/iron-thread/)
[![npm version](https://badge.fury.io/js/iron-thread.svg)](https://www.npmjs.com/package/iron-thread)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Part of Thread Suite](https://img.shields.io/badge/Thread%20Suite-Iron--Thread-black)](https://github.com/eugene001dayne)

---

## The story

You connect an AI model to your database. Most of the time it behaves. Then one day it returns
`{"amount": "about 120"}`, or leaves out a field, or invents a value that looks perfectly plausible.
Your automation crashes, or worse, it doesn't, and the bad data goes in quietly.

Iron-Thread is the checkpoint between the model and your database. It checks every output against a
JSON Schema and blocks what fails.

Then, months later, someone asks: *"Did your system really check that? Can you prove it?"*
Iron-Thread also signs a receipt for every verdict. The receipt can be verified by anyone, offline,
with nothing but your public key.

```
AI output --> Iron-Thread --> valid ....> your database
                          --> invalid ..> blocked, logged, optionally auto-corrected
              every verdict --> a signed receipt, chained to the one before it
```

---

## What it does

- **Validates** AI output against a JSON Schema (Draft 2020-12 by default; a schema's own `$schema` can pick another draft).
- **Scores confidence**: flags values that pass the schema but look statistically unusual compared to past runs.
- **Auto-corrects** failed outputs with Google Gemini and retries (optional, needs `GOOGLE_API_KEY`).
- **Signs a receipt** for every validation, failures included: Ed25519 signature, SHA-256 hash chain.
- **Verifies offline**: a standalone script checks a whole chain with only the public key.
- **Reconciles**: detects stored runs that were edited, deleted or left unsigned after the fact.
- **Alerts** through webhooks, and gives you **analytics** and CSV export.
- **Runs on your machine**: SQLite, no accounts, no hosted service. Your data stays in one local file.

---

## Quickstart (about a minute)

It is tested on Python 3.12 (Linux) and 3.14 (Windows). Other recent versions are likely fine;
automated tests across versions are on the roadmap.

```bash
git clone https://github.com/eugene001dayne/iron-thread
cd iron-thread
python -m venv .venv

# activate it (pick your shell):
source .venv/bin/activate          # macOS / Linux
source .venv/Scripts/activate      # Git Bash on Windows
.venv\Scripts\Activate.ps1         # PowerShell

pip install -r requirements.txt
python -m uvicorn main:app
```

In a second terminal (activate the same environment):

```bash
python examples/quickstart.py
```

You will see something like this:

```
1. created schema 86667ab4...

2. good output: passed  Validation passed
2. bad output : failed  Field 'amount' must be a number, got str

3. the signed receipt for the first run (abridged):
   seq            1
   status         passed
   input_sha256   7940e8fbab56e01ddfa8b3de1b6752253542f44b9f1e4cee
   schema_sha256  1eb197c7a30a1da8a7f9171b9b23b37f37bc71436291ec55
   key_id         aefe34c2abdfdb2d
   signature      9JrU/wYmaqjYB24nYjP4Jh6DTz8vHmU3IWNiP9UHRZQzcvUR...

4. does the receipt match the data? {'valid': True, 'reason': 'ok', 'input_matches': True, 'output_matches': True, 'schema_matches': True}

5. offline check of the whole chain, no server involved: VALID
   OK: 2 entries, all signed by key aefe34c2abdfdb2d. Head hash: caf51c18...

6. do the stored runs still match what was signed? ok=True, runs checked=2, problems=0
```

Interactive API docs are at `http://localhost:8000/docs`.

---

## The receipt

Every call to `POST /validate` returns an `attestation`:

```json
{
  "body": {
    "v": "it-attest/1",
    "chain_id": "<schema id>",
    "seq": 1,
    "prev_hash": "000...0",
    "run_id": "<run id>",
    "status": "passed",
    "input_sha256": "...",
    "output_sha256": "...",
    "schema_sha256": "...",
    "key_id": "...",
    "created_at": "2026-10-18T13:06:23.117557+00:00"
  },
  "entry_hash": "...",
  "signature": "..."
}
```

- Receipts hold **hashes, not your data**. You can show one to an auditor without revealing the content.
- Each receipt stores the hash of the previous one, so changing any old receipt breaks every later link.
- The signature is Ed25519 over the entry hash. Altering a receipt *and recomputing its hash* still fails,
  because only the private key can produce a valid signature.
- Failed validations are receipted too: a record of what was rejected is part of the point.

### What the signature covers, and what it does not

| Covered | Not covered |
|---|---|
| status (passed / failed / corrected) | confidence score and flags |
| hash of the input text | latency, attempts, model name |
| hash of the validated output | the human-readable failure reason |
| hash of the exact schema used | |
| timestamp and position in the chain | |

Things outside the left column can be edited in the database without any receipt noticing.

---

## Verify it yourself, offline

You do not have to trust the server's answer. `verify_offline.py` needs only Python and
`pip install cryptography`. It does not import Iron-Thread and never contacts a server.

```bash
curl -s localhost:8000/attestations/chains/<schema id> > chain.json
curl -s localhost:8000/attestations/keys          # copy "public_key"

python verify_offline.py chain.json --public-key "<public key>"
```

Get the public key from a source you trust (pin it in your own README or release notes), not only from
the server you are checking.

**Pin the head.** A chain that has had its newest entries deleted still verifies by itself. If you
recorded the head hash earlier, in a git commit or a signed release, say so:

```bash
python verify_offline.py chain.json --public-key "<public key>" \
    --expect-head <head hash> --expect-length 42
```

A truncated chain, or one rewritten and re-signed with the same key, will then fail.

### Do the stored runs still match the receipts?

```bash
curl -s localhost:8000/attestations/chains/<schema id>/reconcile
```

Chain verification proves the *receipts* are intact. Reconciliation proves the *data* matches them:
it reports runs whose status, input, output, timestamp or schema were changed after signing, runs with
no receipt, and receipts whose run is missing.

---

## Security

By default Iron-Thread is safe to run on your laptop and refuses to be exposed by accident.

| Mode | How | Behaviour |
|---|---|---|
| Local (default) | no settings | Only requests from this machine, addressed to `localhost`, are accepted. Anyone else gets a `403` that explains how to set a key. |
| API keys | `IRONTHREAD_API_KEYS=key1,key2` | Every endpoint except the public ones needs `Authorization: Bearer <key>` or `X-API-Key: <key>`. |
| Open | `IRONTHREAD_AUTH=off` | No checks. Only for a network you fully trust. |

Generate a key with `python auth.py`. Keys must be at least 16 characters. Listing two keys at once lets
you rotate without downtime.

Public endpoints (no key needed, so strangers can verify a proof): `/`, `/health`, `/docs`,
`GET /attestations/keys` and `POST /attestations/verify`.

Also built in: DNS-rebinding protection (the `Host` header must be `localhost` in local mode), proxy
headers disable the "local" shortcut, and browsers may only call the API from localhost pages unless you set
`IRONTHREAD_CORS_ORIGINS`.

**Honest limits.** There is no TLS (put it behind a reverse proxy for HTTPS), keys are shared secrets
without per-user roles, there is no lockout on repeated failures, and a reverse proxy on the same machine
that adds no forwarding headers would look local, so set a key if you put one in front.

### What this does not protect against

- **The cryptography has not been independently audited.** Do not rely on it for compliance yet.
- Anyone holding the signing key can rewrite history. Pin and publish head hashes to defend against this.
- Automatic anchoring of head hashes is not built yet.
- Canonical JSON is our own simple rule (sorted keys, compact, UTF-8), not full RFC 8785, so number
  formatting could differ between languages.
- Patterns (`"pattern": "..."`) in a schema are regular expressions that run on your machine. Only let
  trusted people create schemas.

---

## Performance

Measured on a Windows laptop, Python 3.14:

| What | Result |
|---|---|
| 100 validations, before receipts | about 0.3 s |
| Validations with a signed receipt on each | about 30 per second |
| One receipt on its own | about 28 ms |

The ~28 ms is one disk sync per receipt, on purpose: a proof that can vanish in a power cut is not much
of a proof. An LLM call takes seconds, so this is rarely the bottleneck. Ordinary tables use a faster
setting. SQLite connections are kept open per thread: opening and closing one per request cost about
98 ms per write on Windows, against 0.1 ms with a persistent connection.

---

## API

| | Endpoint | What it does |
|---|---|---|
| Schemas | `POST /schemas`, `GET /schemas` | Create (invalid JSON Schemas are rejected with 400) and list |
| Validate | `POST /validate`, `POST /validate/batch` | Check output, return the verdict and the receipt |
| Runs | `GET /runs`, `GET /runs/export` | History, CSV export |
| Receipts | `GET /attestations/runs/{run_id}` | One run's receipt |
| | `GET /attestations/chains/{schema_id}` | The whole chain, for offline verification |
| | `GET /attestations/chains/{schema_id}/verify` | Server-side check, returns the head hash |
| | `GET /attestations/chains/{schema_id}/reconcile` | Stored data vs. receipts |
| | `GET /attestations/keys` | Public signing keys (public) |
| | `POST /attestations/verify` | Stateless check of one receipt, optionally against input, output and schema (public) |
| Webhooks | `GET/POST /webhooks`, `DELETE /webhooks/{id}` | Alerts on failure |
| Analytics | `GET /dashboard/stats`, `/analytics/errors`, `/trends`, `/models`, `/schemas` | Overview and breakdowns |
| Legacy | `GET /runs/{run_id}/verify`, `GET /schemas/{id}/chain` | The older unsigned hash chain, kept for compatibility. Prefer receipts. |

The checks follow standard JSON Schema: `type` (including lists such as `["string","null"]`), `required`,
`properties`, `items`, `enum`, `const`, `pattern`, numeric and length limits, `anyOf`/`oneOf`/`allOf`,
`additionalProperties`, local `$ref`, and more. Remote `$ref`s are never fetched. Error messages for the
common cases read like `Field 'amount' must be a number, got str`.

### Confidence scoring

After a run passes validation, values are compared with the history of earlier runs for that schema:
numbers beyond 3 standard deviations, string lengths beyond 3 standard deviations, enum values never seen
before. It switches on after 10 passing runs and needs no AI.

---

## Configuration

Everything is optional. With no configuration at all, Iron-Thread runs locally on SQLite.
A `.env` file in the working directory is loaded automatically; `.env.example` lists every setting.

| Variable | Meaning |
|---|---|
| `IRONTHREAD_DB` | SQLite file (default `ironthread.db`) |
| `ATTEST_KEY_FILE` | Where the signing key file lives (default `ironthread.key`, created on first use) |
| `ATTEST_PRIVATE_KEY` | The signing key itself, base64. Overrides the file. For hosting. |
| `ATTEST_RETIRED_PUBLIC_KEYS` | Comma-separated old public keys that stay trusted after a rotation |
| `IRONTHREAD_API_KEYS` | Comma-separated API keys (see Security) |
| `IRONTHREAD_AUTH` | `off` to run open |
| `IRONTHREAD_CORS_ORIGINS` | Comma-separated browser origins allowed to call the API, or `*` |
| `GOOGLE_API_KEY` | Enables auto-correction with Gemini |
| `SUPABASE_URL`, `SUPABASE_KEY` | Optional legacy storage. If both are set, Supabase is used instead of SQLite. Untested since the move to SQLite. |

**Back up `ironthread.key`.** Without it you cannot extend your chains under the same identity. Never commit
it; it is in `.gitignore`. Publish the *public* key.

---

## SDKs

The published `iron-thread` packages for Python (`pip install iron-thread`) and JavaScript
(`npm install iron-thread`) are version 0.3.0. They default to the old hosted URL, which no longer exists,
so point them at your own server:

```python
from ironthread import IronThread
it = IronThread("http://localhost:8000")
```

They work against a server in default local mode. They do not yet send API keys, and they do not expose
receipts or offline verification: use the HTTP API or `verify_offline.py` for those. An update is planned.

---

## Development

```bash
pip install pytest
pytest -q          # 121 tests
```

| File | Purpose |
|---|---|
| `main.py` | The API |
| `validation.py` | JSON Schema checking and error wording |
| `attestation.py` | Hashing, signing and chain verification |
| `attest_store.py`, `attest_keys.py`, `attest_routes.py` | Receipt storage, key handling, endpoints |
| `reconcile.py` | Stored data vs. receipts |
| `verify_offline.py` | Standalone verifier (depends only on `cryptography`) |
| `auth.py` | API keys, local-only mode, CORS |
| `localdb.py` | SQLite storage with per-thread connections |
| `examples/quickstart.py` | The walk-through above |

---

## Roadmap

Automatic anchoring of head hashes, a JavaScript verifier, updated SDKs, RFC 8785 canonicalization,
an independent review of the cryptography, provider-agnostic auto-correction.

---

## Part of the Thread Suite

Iron-Thread is one of five open-source tools in the Thread Suite, the reliability layer for AI agents.

| Tool | What it does |
|------|-------------|
| **Iron-Thread** | Validates AI output structure before your database |
| **TestThread** | Tests whether your agent behaves correctly |
| **PromptThread** | Versions prompts and tracks performance over time |
| **ChainThread** | Verifies and governs agent-to-agent handoffs |
| **PolicyThread** | Monitors production AI against compliance rules |

---

## License

Apache 2.0. Free to use, modify and distribute. See [LICENSE](LICENSE).

---

*Built by [Eugene Dayne Mawuli](https://github.com/eugene001dayne)*