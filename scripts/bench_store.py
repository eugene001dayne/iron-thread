"""
How fast can signed receipts be appended to the chain, on this machine?

    python scripts/bench_store.py

Each receipt is one fully synced disk write (by design), so this measures your disk's sync latency.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from attest_store import SqliteStore, record_attestation  # noqa: E402
from attestation import generate_keypair  # noqa: E402

priv, _ = generate_keypair()
store = SqliteStore(os.path.join(tempfile.mkdtemp(), "a.db"))
N = 300
t = time.perf_counter()
for i in range(N):
    record_attestation(store, priv, chain_id="c", run_id=f"r{i}", status="passed", raw_input="{}", output={"i": i})
dt = time.perf_counter() - t
print(f"attestation appends: {N / dt:.0f}/s ({dt / N * 1000:.1f} ms each)")
