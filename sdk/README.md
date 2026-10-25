# iron-thread: Python client

The Python client for [Iron-Thread](https://github.com/eugene001dayne/iron-thread): check AI output against a
JSON Schema before it reaches your database, and verify the signed receipt every verdict comes with.

You need an Iron-Thread server. It runs on your own machine in about a minute; see the
[main README](https://github.com/eugene001dayne/iron-thread#quickstart-about-a-minute).

## Install

```bash
pip install iron-thread
pip install "iron-thread[verify]"     # adds offline receipt verification (needs the cryptography package)
```

Python 3.10 or newer. Version 0.4 works with Iron-Thread server 2.x. Earlier releases of this package pointed at
a hosted service that no longer exists.

## Quickstart

```python
from ironthread import IronThread

it = IronThread()    # http://localhost:8000, or $IRONTHREAD_URL

schema = it.create_schema("invoice", {
    "type": "object",
    "required": ["customer", "amount"],
    "properties": {"customer": {"type": "string"}, "amount": {"type": "number", "minimum": 0}},
})

result = it.validate({"customer": "Acme Ltd", "amount": 120.5}, schema["id"])   # dicts are serialised for you
print(result.status, result.reason)            # passed  Validation passed

bad = it.validate('{"customer": "Acme Ltd", "amount": "about 120"}', schema["id"])
print(bad.status, bad.reason)                  # failed  Field 'amount' must be a number, got str
```

## The signed receipt

Every result carries `result.attestation`: an Ed25519-signed, hash-chained record of the input, the output, the
exact schema and the verdict. It holds hashes, not your data.

```python
public_key = "..."   # get it from a source you trust, for example pinned in your own repository

check = it.verify_chain_offline(schema["id"], public_key, expect_head=recorded_head_hash)
if not check:
    raise SystemExit(check.message)      # "entry 2: contents were altered after signing", ...
```

`verify_chain_offline` downloads the chain and checks it **on your machine** (needs `iron-thread[verify]`). Prefer
a public key you did not fetch from the same server, and pass `expect_head` / `expect_length` that you recorded
earlier: that is what catches a chain whose newest entries were deleted.

| Method | What it does |
|---|---|
| `get_attestation(run_id)` | One run's receipt |
| `get_chain(schema_id)` | Every receipt for a schema, oldest first |
| `verify_chain_offline(...)` | Check a chain yourself, locally |
| `verify_chain_remote(schema_id)` | Ask the server (you are trusting its answer) |
| `verify_attestation(entry, input=, output=, schema_definition=)` | Check one receipt against your data |
| `reconcile(schema_id)` | Do the stored runs still match what was signed? |
| `public_keys()` | The server's public signing keys |

`ironthread.verify_chain(entries, public_key, ...)` is the same check as a plain function, with no client or
network involved.

## API keys

A server in its default mode only accepts requests from its own machine. If it uses API keys:

```python
it = IronThread("https://your-server", api_key="it_...")     # or set $IRONTHREAD_API_KEY
```

## Errors

Server errors raise `IronThreadError` (a subclass of `httpx.HTTPStatusError`) with `.status_code` and the
server's own explanation in `.detail`. If the server cannot be reached you get an `httpx.ConnectError` that says
how to start it.

## Other methods

`list_schemas`, `validate_batch`, `runs`, `export_csv`, `stats`, `analytics_errors`, `analytics_trends`,
`analytics_models`, `analytics_schemas`, `create_webhook`, `list_webhooks`, `delete_webhook`, `health`.
`verify_run` and `get_schema_chain` use the older unsigned hash chain; prefer the receipts.

Apache 2.0. Part of the [Thread Suite](https://github.com/eugene001dayne).
