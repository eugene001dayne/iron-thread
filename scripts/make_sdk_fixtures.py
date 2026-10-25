"""
Regenerate the cross-language fixtures that the JavaScript SDK tests use.

    python scripts/make_sdk_fixtures.py

Run it only when the receipt format or the canonical-JSON rule changes. The fixtures are produced by the
PYTHON implementation, and the JavaScript tests must reproduce them exactly: that is the proof that the two
languages agree. The signing key is generated fresh and thrown away; only the public key is kept.
"""
import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from attestation import GENESIS, canonical, generate_keypair, key_id, make_entry, sha256_hex  # noqa: E402

OUT = ROOT / "sdk" / "iron-thread-js" / "test" / "fixtures"


def build_chain():
    priv_b64, pub_b64 = generate_keypair()
    priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(priv_b64))
    entries, prev = [], GENESIS
    for i in range(1, 4):
        e = make_entry(priv_b64, chain_id="fixture-chain", seq=i, prev_hash=prev, run_id=f"run-{i}",
                       status="passed" if i != 2 else "failed", raw_input=f'{{"n": {i}}}',
                       output={"n": i} if i != 2 else None, schema_definition={"type": "object"})
        entries.append(e)
        prev = e["entry_hash"]
    # Two entries whose bodies carry awkward-but-valid content, to prove both languages canonicalise it identically.
    awkward = [
        {"note": "h\u00e9llo \U0001F642 \u2028 \"quoted\" \\ back\tslash", "\uff5e": 1, "\U0001F600": 2, "a": 3},
        {"nested": {"z": [3, 2, {"b": 1, "a": 0}], "x": None}, "": "empty key", "B": 1, "ab": 2, "a": 3},
    ]
    for extra in awkward:
        body = {
            "v": "it-attest/1", "chain_id": "fixture-chain", "seq": len(entries) + 1, "prev_hash": prev,
            "run_id": f"run-{len(entries) + 1}", "status": "passed", "input_sha256": sha256_hex(b"x"),
            "output_sha256": None, "schema_sha256": None, "key_id": key_id(pub_b64),
            "created_at": "2026-10-24T10:00:00+00:00", "extra": extra,
        }
        entry_hash = sha256_hex(canonical(body))
        entries.append({"body": body, "entry_hash": entry_hash,
                        "signature": base64.b64encode(priv.sign(bytes.fromhex(entry_hash))).decode()})
        prev = entry_hash
    return {"public_key": pub_b64, "key_id": key_id(pub_b64), "head": prev, "entries": entries}


CANONICAL_CASES = [
    ("keys are sorted", '{"b":1,"a":2}', False),
    ("nesting", '{"z":{"y":[3,2,{"b":1,"a":0}],"x":null},"a":true}', False),
    ("unicode", '{"\u00e9":"h\u00e9llo","\u65e5\u672c\u8a9e":"\u30c6\u30b9\u30c8"}', False),
    ("astral characters sort by code point, not UTF-16 unit", '{"\\uff5e":1,"\\ud83d\\ude00":2,"a":3}', False),
    ("escapes", '{"q":"say \\"hi\\"\\n\\ttab \\\\ back \\u0001 \\u007f \\u2028"}', False),
    ("empty containers", '{"a":{},"b":[],"c":""}', False),
    ("integers", '{"n":[0,-1,42,1000000,9007199254740991]}', False),
    ("prefix keys", '{"ab":1,"a":2,"":3,"B":4}', False),
    ("floats are the one known difference", '{"f":1.0,"g":0.5}', True),
]


def build_cases():
    return [{"name": name, "json": text, "expected": canonical(json.loads(text)).decode("utf-8"),
             "known_difference": known} for name, text, known in CANONICAL_CASES]


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "chain.json").write_text(json.dumps(build_chain(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "canonical_cases.json").write_text(json.dumps(build_cases(), indent=2, ensure_ascii=False) + "\n",
                                              encoding="utf-8")
    print("wrote", OUT / "chain.json")
    print("wrote", OUT / "canonical_cases.json")
