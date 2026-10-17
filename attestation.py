"""Iron-Thread attestation primitives (Step 3): hash, sign, verify ONE entry."""
import base64
import hashlib
import json
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

GENESIS = "0" * 64  # prev_hash of the very first entry in a chain


def canonical(obj) -> bytes:
    """Same data -> same bytes, always. Sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_keypair():
    """Returns (private_b64, public_b64): raw 32-byte keys, base64-encoded."""
    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(priv_raw).decode(), base64.b64encode(pub_raw).decode()


def key_id(public_b64: str) -> str:
    """Short fingerprint so an entry says WHICH key signed it."""
    return sha256_hex(base64.b64decode(public_b64))[:16]


def make_entry(private_b64, *, chain_id, seq, prev_hash, run_id, status, raw_input, output):
    """Build the body, hash it, sign the hash. Returns the full entry."""
    priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_b64))
    pub_b64 = base64.b64encode(
        priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()

    body = {
        "v": "it-attest/1",
        "chain_id": chain_id,
        "seq": seq,
        "prev_hash": prev_hash,
        "run_id": run_id,
        "status": status,
        "input_sha256": sha256_hex(raw_input.encode("utf-8")),
        "output_sha256": sha256_hex(canonical(output)) if output is not None else None,
        "key_id": key_id(pub_b64),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    entry_hash = sha256_hex(canonical(body))
    signature = priv.sign(bytes.fromhex(entry_hash))
    return {"body": body, "entry_hash": entry_hash, "signature": base64.b64encode(signature).decode()}


def verify_entry(entry, public_b64):
    """Uses ONLY the entry and the public key. Returns (ok, reason)."""
    try:
        body = entry["body"]
        if sha256_hex(canonical(body)) != entry["entry_hash"]:
            return False, "body was altered (hash mismatch)"
        if body["key_id"] != key_id(public_b64):
            return False, "signed by a different key"
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
        pub.verify(base64.b64decode(entry["signature"]), bytes.fromhex(entry["entry_hash"]))
        return True, "ok"
    except InvalidSignature:
        return False, "signature invalid"
    except (KeyError, ValueError, TypeError) as e:
        return False, f"malformed entry: {e}"