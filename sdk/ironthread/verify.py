"""
Offline verification of Iron-Thread receipts.

Needs the `cryptography` package:  pip install "iron-thread[verify]"
Nothing here talks to a server. This is a port of the standalone verify_offline.py in the Iron-Thread
repository, and a test keeps the two in agreement.
"""
import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Optional

GENESIS = "0" * 64


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    message: str

    def __bool__(self):
        return self.ok


def canonical(obj) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8. Must match the server byte for byte."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_chain(entries: list, public_key: str, expect_head: Optional[str] = None,
                 expect_length: Optional[int] = None) -> VerifyResult:
    """
    entries:      the list returned by IronThread.get_chain(), oldest first
    public_key:   base64 Ed25519 public key you trust
    expect_head:  the head hash you recorded or published earlier (catches truncation and rewriting)
    expect_length: the number of entries you expect
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as e:
        raise ImportError(
            "Offline verification needs the 'cryptography' package: pip install \"iron-thread[verify]\"") from e

    if not entries:
        return VerifyResult(False, "the chain is empty")
    try:
        raw = base64.b64decode(public_key)
        key = Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError):
        return VerifyResult(False, "the public key is not a valid base64 Ed25519 key")
    key_id = _sha256_hex(raw)[:16]

    prev = GENESIS
    for i, entry in enumerate(entries, start=1):
        try:
            body = entry["body"]
            if body.get("seq") != i:
                return VerifyResult(False, f"entry {i}: sequence number is {body.get('seq')} "
                                           "(gap, reorder, or missing start)")
            if body.get("prev_hash") != prev:
                return VerifyResult(False, f"entry {i}: broken link to the previous entry")
            if body.get("key_id") != key_id:
                return VerifyResult(False, f"entry {i}: signed by a different key than the one you supplied")
            if _sha256_hex(canonical(body)) != entry["entry_hash"]:
                return VerifyResult(False, f"entry {i}: contents were altered after signing")
            key.verify(base64.b64decode(entry["signature"]), bytes.fromhex(entry["entry_hash"]))
        except InvalidSignature:
            return VerifyResult(False, f"entry {i}: signature is not valid for this key")
        except (KeyError, ValueError, TypeError, AttributeError) as e:
            return VerifyResult(False, f"entry {i}: malformed ({type(e).__name__}: {e})")
        prev = entry["entry_hash"]

    if expect_length is not None and len(entries) != expect_length:
        return VerifyResult(False, f"chain has {len(entries)} entries but you expected {expect_length} "
                                   "(entries removed or added)")
    if expect_head is not None and prev != expect_head:
        return VerifyResult(False, "the newest entry's hash does not match the head you expected "
                                   "(truncated or rewritten)")
    return VerifyResult(True, f"OK: {len(entries)} entries, all signed by key {key_id}. Head hash: {prev}")
