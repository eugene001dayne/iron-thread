#!/usr/bin/env python3
"""
Independent verifier for Iron-Thread attestation chains.

Needs only Python 3.9+ and:  pip install cryptography
It does NOT import Iron-Thread and does NOT talk to any server. You give it an exported chain and
the public key; it tells you whether the chain is intact and signed by that key.

  python verify_offline.py chain.json --public-key <base64>
  python verify_offline.py chain.json --public-key <base64> --expect-head <hex> --expect-length 42

Get chain.json from:  GET /attestations/chains/<chain_id>
Get the public key from a source you trust (pinned in a README, a signed release, etc.)
and, ideally, a head hash you recorded or published earlier: --expect-head is what catches
a chain whose newest entries were silently deleted, or one that was rewritten and re-signed.
"""
import argparse
import base64
import hashlib
import json
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

GENESIS = "0" * 64


def canonical(obj):
    """Deterministic JSON: sorted keys, no whitespace, UTF-8. (Re-implemented on purpose.)"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def verify(entries, public_b64, expect_head=None, expect_length=None):
    """Returns (ok, message). Pure function: no files, no network."""
    if not entries:
        return False, "the chain is empty"
    try:
        raw = base64.b64decode(public_b64)
        public_key = Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError):
        return False, "the public key is not a valid base64 Ed25519 key"
    key_id = sha256_hex(raw)[:16]

    prev = GENESIS
    for i, entry in enumerate(entries, start=1):
        try:
            body = entry["body"]
            if body.get("seq") != i:
                return False, f"entry {i}: sequence number is {body.get('seq')} (gap, reorder, or missing start)"
            if body.get("prev_hash") != prev:
                return False, f"entry {i}: broken link to the previous entry"
            if body.get("key_id") != key_id:
                return False, f"entry {i}: signed by a different key than the one you supplied"
            if sha256_hex(canonical(body)) != entry["entry_hash"]:
                return False, f"entry {i}: contents were altered after signing"
            public_key.verify(base64.b64decode(entry["signature"]), bytes.fromhex(entry["entry_hash"]))
        except InvalidSignature:
            return False, f"entry {i}: signature is not valid for this key"
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            return False, f"entry {i}: malformed ({type(e).__name__}: {e})"
        prev = entry["entry_hash"]

    if expect_length is not None and len(entries) != expect_length:
        return False, f"chain has {len(entries)} entries but you expected {expect_length} (entries removed or added)"
    if expect_head is not None and prev != expect_head:
        return False, "the newest entry's hash does not match the head you expected (truncated or rewritten)"
    return True, f"OK: {len(entries)} entries, all signed by key {key_id}. Head hash: {prev}"


def main():
    parser = argparse.ArgumentParser(description="Verify an Iron-Thread attestation chain offline.")
    parser.add_argument("chain_file", help="JSON from GET /attestations/chains/<id> (or a plain list of entries)")
    parser.add_argument("--public-key", required=True, help="base64 Ed25519 public key you trust")
    parser.add_argument("--expect-head", help="head hash you recorded or published earlier")
    parser.add_argument("--expect-length", type=int, help="number of entries you expect")
    args = parser.parse_args()

    with open(args.chain_file, encoding="utf-8") as f:
        data = json.load(f)
    entries = data["entries"] if isinstance(data, dict) else data

    ok, message = verify(entries, args.public_key, args.expect_head, args.expect_length)
    print(("VALID  " if ok else "INVALID  ") + message)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
