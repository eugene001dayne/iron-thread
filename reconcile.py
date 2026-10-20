"""
Does the data in `validation_runs` still match what was signed?

Chain verification only proves the PROOFS are intact. This checks the DATA against them, and finds
runs with no proof (a crash between the two writes) and proofs with no run (a deleted run).
Pure functions: no database, no network.
"""
from datetime import datetime

from attestation import canonical, sha256_hex

MAX_FINDINGS = 100


def _finding(run_id, problem, detail):
    return {"run_id": run_id, "problem": problem, "detail": detail}


def _same_instant(a, b):
    """Timestamps compare as instants, so '+00:00' vs 'Z' formatting from another database is not an alarm."""
    if a == b:
        return True
    try:
        return datetime.fromisoformat(str(a).replace("Z", "+00:00")) == datetime.fromisoformat(str(b).replace("Z", "+00:00"))
    except ValueError:
        return False


def reconcile(runs, entries, schema_definition=None):
    """
    runs:    rows of validation_runs for ONE schema.
    entries: that schema's attestation chain entries.
    schema_definition: the schema as stored now (None = skip the schema check).
    """
    by_run = {e["body"]["run_id"]: e for e in entries}
    seen, findings = set(), []

    for run in runs:
        rid = run["id"]
        seen.add(rid)
        entry = by_run.get(rid)
        if entry is None:
            findings.append(_finding(rid, "unattested_run", "no signed attestation exists for this run"))
            continue
        body = entry["body"]

        if run.get("status") != body.get("status"):
            findings.append(_finding(rid, "status_mismatch",
                                     f"stored status is '{run.get('status')}', signed status is '{body.get('status')}'"))
        if sha256_hex((run.get("raw_ai_output") or "").encode("utf-8")) != body.get("input_sha256"):
            findings.append(_finding(rid, "input_mismatch", "the stored input no longer matches what was signed"))
        out = run.get("validated_output")
        if (None if out is None else sha256_hex(canonical(out))) != body.get("output_sha256"):
            findings.append(_finding(rid, "output_mismatch", "the stored output no longer matches what was signed"))
        if not _same_instant(run.get("created_at"), body.get("created_at")):
            findings.append(_finding(rid, "timestamp_mismatch", "the stored timestamp differs from the signed one"))
        if (schema_definition is not None and body.get("schema_sha256") is not None
                and sha256_hex(canonical(schema_definition)) != body["schema_sha256"]):
            findings.append(_finding(rid, "schema_mismatch",
                                     "the schema as stored now is not the schema this run was checked against"))

    for rid in by_run:
        if rid not in seen:
            findings.append(_finding(rid, "orphan_attestation", "a signed attestation exists but the run is missing"))

    return {
        "ok": not findings,
        "runs_checked": len(runs),
        "attestations_checked": len(entries),
        "findings_total": len(findings),
        "findings": findings[:MAX_FINDINGS],
    }
