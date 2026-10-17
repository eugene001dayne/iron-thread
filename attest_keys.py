"""Signing-key management. The private key never touches git or the database."""
import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from attestation import generate_keypair, key_id


def load_or_create_private_key(path=None) -> str:
    """
    Order: ATTEST_PRIVATE_KEY env var (production) -> key file (self-hosters) -> create file.
    Never overwrites an existing key file.
    """
    env = os.getenv("ATTEST_PRIVATE_KEY")
    if env:
        return env.strip()

    p = Path(path or os.getenv("ATTEST_KEY_FILE", "ironthread.key"))
    try:
        priv, _ = generate_keypair()
        with open(p, "x") as f:  # "x" = fail if the file already exists
            f.write(priv + "\n")
        try:
            os.chmod(p, 0o600)  # owner-only on Linux/macOS (mostly a no-op on Windows)
        except OSError:
            pass
        return priv
    except FileExistsError:
        return p.read_text().strip()


def public_from_private(priv_b64: str) -> str:
    priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(priv_b64))
    raw = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def trusted_public_keys(priv_b64: str) -> dict:
    """
    {key_id: public_b64} for the current key plus any retired keys, so old
    entries stay verifiable after a rotation. Retired keys: ATTEST_RETIRED_PUBLIC_KEYS=pub1,pub2
    """
    keys = {}
    current = public_from_private(priv_b64)
    keys[key_id(current)] = current
    for pub in filter(None, (s.strip() for s in os.getenv("ATTEST_RETIRED_PUBLIC_KEYS", "").split(","))):
        keys[key_id(pub)] = pub
    return keys
