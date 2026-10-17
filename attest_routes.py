"""Public attestation API: publish keys, fetch proofs, verify proofs."""
import os
from functools import lru_cache
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from attest_keys import load_or_create_private_key, trusted_public_keys
from attest_store import SqliteStore
from attestation import canonical, sha256_hex, verify_chain, verify_entry

router = APIRouter(prefix="/attestations", tags=["attestations"])


@lru_cache
def get_ctx():
    priv = load_or_create_private_key()
    return {
        "store": SqliteStore(os.getenv("ATTEST_DB", "ironthread.db")),
        "priv": priv,
        "keys": trusted_public_keys(priv),
    }


@router.get("/keys")
def public_keys(ctx=Depends(get_ctx)):
    """The public keys that sign our attestations. Safe to publish, pin and cache."""
    return {
        "algorithm": "Ed25519",
        "keys": [{"key_id": kid, "public_key": pub} for kid, pub in ctx["keys"].items()],
    }


@router.get("/runs/{run_id}")
def get_attestation(run_id: str, ctx=Depends(get_ctx)):
    entry = ctx["store"].by_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="No attestation for this run")
    return entry


@router.get("/chains/{chain_id}")
def export_chain(chain_id: str, ctx=Depends(get_ctx)):
    """Full chain for OFFLINE verification: you don't have to trust our /verify answer."""
    entries = ctx["store"].chain(chain_id)
    if not entries:
        raise HTTPException(status_code=404, detail="Unknown chain")
    return {"chain_id": chain_id, "entries": entries}


@router.get("/chains/{chain_id}/verify")
def verify_chain_endpoint(chain_id: str, ctx=Depends(get_ctx)):
    entries = ctx["store"].chain(chain_id)
    if not entries:
        raise HTTPException(status_code=404, detail="Unknown chain")
    ok, reason = verify_chain(entries, ctx["keys"])
    return {
        "chain_id": chain_id,
        "valid": ok,
        "reason": reason,
        "length": len(entries),
        "head_hash": entries[-1]["entry_hash"],  # <- this is what you anchor publicly (Step 9)
    }


class VerifyRequest(BaseModel):
    entry: dict
    input: Optional[str] = None   # the raw AI output you claim was evaluated
    output: Optional[Any] = None  # the validated output you claim came back


@router.post("/verify")
def verify_proof(req: VerifyRequest, ctx=Depends(get_ctx)):
    """Stateless: needs only the entry (+ optional original data). Doesn't touch our database."""
    body = req.entry.get("body", {}) if isinstance(req.entry, dict) else {}
    pub = ctx["keys"].get(body.get("key_id"))
    if pub is None:
        return {"valid": False, "reason": "unknown key_id"}
    ok, reason = verify_entry(req.entry, pub)
    result = {"valid": ok, "reason": reason}
    if ok and req.input is not None:
        result["input_matches"] = sha256_hex(req.input.encode("utf-8")) == body.get("input_sha256")
    if ok and req.output is not None:
        result["output_matches"] = sha256_hex(canonical(req.output)) == body.get("output_sha256")
    return result
