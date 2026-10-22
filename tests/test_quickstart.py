import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "quickstart.py"


def test_a_missing_server_gets_a_friendly_message_not_a_traceback():
    # port 9 (discard) is closed on virtually every machine, so the connection is refused immediately
    p = subprocess.run([sys.executable, str(SCRIPT), "http://127.0.0.1:9"], capture_output=True, text=True)
    assert p.returncode == 1
    assert "Cannot reach Iron-Thread" in p.stderr and "python -m uvicorn main:app" in p.stderr
    assert "Traceback" not in p.stderr
