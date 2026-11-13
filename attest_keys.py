"""Signing-key management. The private key never touches git or the database."""
import base64
import binascii
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from attestation import generate_keypair, key_id

FIX = ("Restore the key from your backup. If it is truly lost, move the file aside and restart to create a new "
       "one; receipts signed with the lost key can then no longer be extended or verified. "
       "The server never overwrites an existing key file.")


class KeyProblem(Exception):
    """
    The signing key cannot be used. str(error) says what is wrong and how to fix it (for logs and for
    authenticated callers). `code` is a short reason that is safe to show publicly.
    """

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _check(text, source):
    """Return the key if `text` is a valid signing key (one line, base64, 32 bytes); otherwise raise KeyProblem."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise KeyProblem(f"The signing key in {source} is empty. {FIX}", "empty")
    if len(lines) > 1:
        raise KeyProblem(f"The signing key in {source} has {len(lines)} lines; a key is exactly one line. "
                         f"Extra text was probably added by accident. {FIX}", "multiple_lines")
    key = lines[0].strip()
    try:
        raw = base64.b64decode(key, validate=True)
    except (binascii.Error, ValueError):
        raise KeyProblem(f"The signing key in {source} is not valid base64. {FIX}", "wrong_format") from None
    if len(raw) != 32:
        raise KeyProblem(f"The signing key in {source} decodes to {len(raw)} bytes, not 32. {FIX}",
                         "wrong_size")
    return key


def _key_file(path=None):
    return Path(path or os.getenv("ATTEST_KEY_FILE", "ironthread.key"))


def _read(p):
    try:
        return p.read_text(encoding="utf-8-sig")  # utf-8-sig: tolerate the BOM that Notepad adds
    except OSError as e:
        raise KeyProblem(f"The signing key file {p} cannot be read ({e.__class__.__name__}). {FIX}",
                         "unreadable") from e


def load_or_create_private_key(path=None) -> str:
    """
    Order: ATTEST_PRIVATE_KEY env var (production) -> key file (self-hosters) -> create file.
    Never overwrites an existing key file. Raises KeyProblem, with instructions, if what it finds is unusable.
    """
    env = os.getenv("ATTEST_PRIVATE_KEY")
    if env:
        return _check(env, "the ATTEST_PRIVATE_KEY environment variable")

    p = _key_file(path)
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
        return _check(_read(p), str(p))


def signing_key_status(path=None) -> dict:
    """
    Is the signing key usable? Never creates the key and never raises.
      {"status": "ok", "key_id": ...}  |  {"status": "will_be_created"}
      {"status": "error", "problem": <code>, "message": <full explanation: keep it out of public output>}
    """
    try:
        env = os.getenv("ATTEST_PRIVATE_KEY")
        if env:
            key = _check(env, "the ATTEST_PRIVATE_KEY environment variable")
        else:
            p = _key_file(path)
            if not p.exists():
                return {"status": "will_be_created"}
            key = _check(_read(p), str(p))
        return {"status": "ok", "key_id": key_id(public_from_private(key))}
    except KeyProblem as e:
        return {"status": "error", "problem": e.code, "message": str(e)}


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
