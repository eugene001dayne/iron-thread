"""
Throughput of the validation path (SQLite, no HTTP): how many validations per second, as the table grows.

    python scripts/bench.py

Uses a temporary database and a temporary signing key, so it never touches your real data. Signing a receipt
costs one disk sync, so the number depends mostly on how fast your disk confirms a write.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

work = tempfile.mkdtemp()
os.environ["IRONTHREAD_DB"] = os.path.join(work, "bench.db")
os.environ["ATTEST_KEY_FILE"] = os.path.join(work, "bench.key")
os.environ["IRONTHREAD_AUTH"] = "off"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402

main.SUPABASE_URL = main.SUPABASE_KEY = None

from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(main.app)
sid = c.post("/schemas", json={"name": "b", "schema_definition": {
    "type": "object", "required": ["amount"], "properties": {"amount": {"type": "number"}}}}).json()["id"]

n = 0
for total in (200, 1000):
    t = time.perf_counter()
    for i in range(total):
        main.run_validation(sid, '{"amount": %d}' % i, None, False)
    dt = time.perf_counter() - t
    with main.get_client() as cl:
        n = len(cl.get("/validation_runs").json())
    print(f"+{total} runs in {dt:.1f}s -> {total / dt:.0f} runs/s (table now {n} rows)")

t = time.perf_counter()
c.get("/dashboard/stats")
print(f"/dashboard/stats at {n} rows: {time.perf_counter() - t:.3f}s")
t = time.perf_counter()
c.get("/runs/export")
print(f"/runs/export at {n} rows: {time.perf_counter() - t:.3f}s")
