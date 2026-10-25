"""The JavaScript SDK tests use fixtures made by the Python code. These tests stop those fixtures going stale."""
import json
from pathlib import Path

import verify_offline
from attestation import canonical

FIXTURES = Path(__file__).resolve().parents[1] / "sdk" / "iron-thread-js" / "test" / "fixtures"


def test_the_committed_chain_fixture_still_verifies_with_the_python_verifier():
    chain = json.loads((FIXTURES / "chain.json").read_text(encoding="utf-8"))
    ok, message = verify_offline.verify(chain["entries"], chain["public_key"], chain["head"], 5)
    assert ok, message


def test_the_canonical_json_fixtures_still_match_what_python_produces():
    cases = json.loads((FIXTURES / "canonical_cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 8
    for case in cases:
        assert canonical(json.loads(case["json"])).decode("utf-8") == case["expected"], (
            f"{case['name']}: Python's canonical JSON changed. If that is intentional it is a format change: "
            "bump the receipt version, regenerate with scripts/make_sdk_fixtures.py, and update every SDK.")
