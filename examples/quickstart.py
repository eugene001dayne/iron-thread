"""
Iron-Thread quickstart: check two AI outputs, then verify the signed receipts.

    python -m uvicorn main:app          # in one terminal
    python examples/quickstart.py       # in another  (optional: pass a different server URL)

If your server uses API keys, put one in the IRONTHREAD_API_KEY environment variable first.
"""
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_offline import verify  # the standalone verifier: it never talks to the server

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
KEY = os.getenv("IRONTHREAD_API_KEY")
http = httpx.Client(base_url=BASE, timeout=30, headers={"Authorization": f"Bearer {KEY}"} if KEY else {})

SCHEMA = {
    "type": "object",
    "required": ["customer", "amount"],
    "properties": {
        "customer": {"type": "string", "minLength": 2},
        "amount": {"type": "number", "minimum": 0},
    },
}

try:
    created = http.post("/schemas", json={"name": "invoice", "schema_definition": SCHEMA})
except httpx.ConnectError:
    sys.exit(f"Cannot reach Iron-Thread at {BASE}.\n"
             "Start the server first, in another terminal:\n"
             "    python -m uvicorn main:app\n"
             "then run this script again.")
if created.status_code in (401, 403):
    sys.exit(f"The server refused the request ({created.status_code}): {created.json().get('detail', '')}\n"
             "If it uses API keys, put one in the IRONTHREAD_API_KEY environment variable and try again.")
if created.status_code >= 400:
    sys.exit(f"The server answered {created.status_code}: {created.text[:300]}")
schema = created.json()
print(f"1. created schema {schema['id'][:8]}...\n")

good = '{"customer": "Acme Ltd", "amount": 120.5}'
bad = '{"customer": "Acme Ltd", "amount": "about 120"}'

runs = []
for label, text in (("good output", good), ("bad output ", bad)):
    run = http.post("/validate", json={"schema_id": schema["id"], "ai_output": text}).json()
    runs.append(run)
    print(f"2. {label}: {run['status']:<7} {run['reason']}")

print("\n3. the signed receipt for the first run (abridged):")
receipt = runs[0]["attestation"]
for field in ("seq", "status", "input_sha256", "schema_sha256", "key_id"):
    print(f"   {field:<14} {str(receipt['body'][field])[:48]}")
print(f"   {'signature':<14} {receipt['signature'][:48]}...")

check = http.post("/attestations/verify", json={
    "entry": receipt, "input": good, "output": runs[0]["data"], "schema_definition": SCHEMA}).json()
print(f"\n4. does the receipt match the data? {check}")

chain = http.get(f"/attestations/chains/{schema['id']}").json()["entries"]
public_key = http.get("/attestations/keys").json()["keys"][0]["public_key"]
ok, message = verify(chain, public_key)
print(f"\n5. offline check of the whole chain, no server involved: {'VALID' if ok else 'INVALID'}")
print(f"   {message}")

report = http.get(f"/attestations/chains/{schema['id']}/reconcile").json()
print(f"\n6. do the stored runs still match what was signed? ok={report['ok']}, "
      f"runs checked={report['runs_checked']}, problems={report['findings_total']}")

# Exit non-zero if anything was off, so CI (and scripts) can tell.
sys.exit(0 if check["valid"] and ok and report["ok"] else 1)
