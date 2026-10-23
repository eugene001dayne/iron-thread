"""
Where does the time go? Profiles 100 validations and prints the 8 most expensive functions.

    python scripts/prof.py

Look at the `tottime` column. This is how we found that opening and closing a SQLite connection per request
cost ~98 ms per write on Windows (see the README's Performance section).
"""
import cProfile
import os
import pstats
import sys
import tempfile
from pathlib import Path

work = tempfile.mkdtemp()
os.environ["IRONTHREAD_DB"] = os.path.join(work, "prof.db")
os.environ["ATTEST_KEY_FILE"] = os.path.join(work, "prof.key")
os.environ["IRONTHREAD_AUTH"] = "off"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402

main.SUPABASE_URL = main.SUPABASE_KEY = None

from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(main.app)
sid = c.post("/schemas", json={"name": "p", "schema_definition": {
    "type": "object", "required": ["amount"], "properties": {"amount": {"type": "number"}}}}).json()["id"]

pr = cProfile.Profile()
pr.enable()
for i in range(100):
    main.run_validation(sid, '{"amount": %d}' % i, None, False)
pr.disable()
pstats.Stats(pr).sort_stats("tottime").print_stats(8)
