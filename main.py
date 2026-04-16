import os
import re
import json
import csv
import hashlib
import statistics
import io
import uuid
from datetime import datetime, timezone
from typing import Optional, Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Iron-Thread",
    description="Open-source middleware that validates AI outputs before they reach your database.",
    version="1.2.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────

def get_client():
    return httpx.Client(
        base_url=f"{SUPABASE_URL}/rest/v1",
        headers=HEADERS,
        timeout=15.0
    )


# ─────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────

class SchemaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    schema_definition: dict

class ValidateRequest(BaseModel):
    schema_id: str
    ai_output: str
    model_used: Optional[str] = None
    auto_correct: bool = False

class BatchValidateRequest(BaseModel):
    schema_id: str
    ai_outputs: list[str]
    model_used: Optional[str] = None

class WebhookCreate(BaseModel):
    name: str
    url: str
    on_failure: bool = True
    on_success: bool = False
    schema_id: Optional[str] = None


# ─────────────────────────────────────────────
# VALIDATION ENGINE
# ─────────────────────────────────────────────

def validate_against_schema(data: Any, schema: dict, path: str = "") -> list[str]:
    errors = []

    required = schema.get("required", [])
    for field in required:
        if not isinstance(data, dict) or field not in data:
            errors.append(f"Missing required field: '{field}'")

    properties = schema.get("properties", {})
    if isinstance(data, dict):
        for field, field_schema in properties.items():
            if field not in data:
                continue
            value = data[field]
            field_path = f"{path}.{field}" if path else field
            field_type = field_schema.get("type")

            # Type checks
            if field_type == "string" and not isinstance(value, str):
                errors.append(f"Field '{field_path}' must be a string, got {type(value).__name__}")
            elif field_type == "integer" and not isinstance(value, int):
                errors.append(f"Field '{field_path}' must be an integer, got {type(value).__name__}")
            elif field_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"Field '{field_path}' must be a number, got {type(value).__name__}")
            elif field_type == "boolean" and not isinstance(value, bool):
                errors.append(f"Field '{field_path}' must be a boolean, got {type(value).__name__}")
            elif field_type == "array" and not isinstance(value, list):
                errors.append(f"Field '{field_path}' must be an array, got {type(value).__name__}")
            elif field_type == "object" and not isinstance(value, dict):
                errors.append(f"Field '{field_path}' must be an object, got {type(value).__name__}")

            # String constraints
            if isinstance(value, str):
                if "minLength" in field_schema and len(value) < field_schema["minLength"]:
                    errors.append(f"Field '{field_path}' length {len(value)} is below minimum {field_schema['minLength']}")
                if "maxLength" in field_schema and len(value) > field_schema["maxLength"]:
                    errors.append(f"Field '{field_path}' length {len(value)} exceeds maximum {field_schema['maxLength']}")
                if "pattern" in field_schema and not re.match(field_schema["pattern"], value):
                    errors.append(f"Field '{field_path}' does not match pattern '{field_schema['pattern']}'")

            # Numeric constraints
            if isinstance(value, (int, float)):
                if "minimum" in field_schema and value < field_schema["minimum"]:
                    errors.append(f"Field '{field_path}' value {value} is below minimum {field_schema['minimum']}")
                if "maximum" in field_schema and value > field_schema["maximum"]:
                    errors.append(f"Field '{field_path}' value {value} exceeds maximum {field_schema['maximum']}")

            # Enum
            if "enum" in field_schema and value not in field_schema["enum"]:
                errors.append(f"Field '{field_path}' value '{value}' is not in allowed enum {field_schema['enum']}")

            # Array constraints
            if isinstance(value, list):
                if "minItems" in field_schema and len(value) < field_schema["minItems"]:
                    errors.append(f"Field '{field_path}' has {len(value)} items, minimum is {field_schema['minItems']}")
                if "maxItems" in field_schema and len(value) > field_schema["maxItems"]:
                    errors.append(f"Field '{field_path}' has {len(value)} items, maximum is {field_schema['maxItems']}")

            # Nested object
            if field_type == "object" and isinstance(value, dict):
                nested_errors = validate_against_schema(value, field_schema, field_path)
                errors.extend(nested_errors)

    return errors


# ─────────────────────────────────────────────
# GEMINI AUTO-CORRECTION
# ─────────────────────────────────────────────

def auto_correct_with_gemini(raw_output: str, error_reason: str, schema_definition: dict) -> Optional[str]:
    if not GEMINI_AVAILABLE or not GOOGLE_API_KEY:
        return None
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        prompt = f"""You are a JSON correction assistant.

The following JSON output failed validation:
{raw_output}

Validation error: {error_reason}

Required schema:
{json.dumps(schema_definition, indent=2)}

Return ONLY a corrected JSON object that passes validation.
No explanation, no markdown, no code blocks. Just the raw JSON."""

        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt
        )
        return response.text.strip()
    except Exception:
        return None


# ─────────────────────────────────────────────
# WEBHOOK FIRING
# ─────────────────────────────────────────────

def fire_webhooks(schema_id: Optional[str], run_id: str, status: str, reason: str, model_used: Optional[str], latency_ms: Optional[int]):
    try:
        with get_client() as client:
            params = {"active": "eq.true"}
            if schema_id:
                params["or"] = f"(schema_id.eq.{schema_id},schema_id.is.null)"
            resp = client.get("/webhooks", params=params)
            if resp.status_code != 200:
                return
            webhooks = resp.json()

        payload = {
            "event": f"validation.{status}",
            "schema_id": schema_id,
            "run": {
                "run_id": run_id,
                "status": status,
                "reason": reason,
                "model_used": model_used,
                "latency_ms": latency_ms
            },
            "timestamp": int(datetime.now(timezone.utc).timestamp())
        }

        for webhook in webhooks:
            should_fire = (status == "failed" and webhook.get("on_failure")) or \
                          (status in ("passed", "corrected") and webhook.get("on_success"))
            if should_fire:
                try:
                    httpx.post(webhook["url"], json=payload, timeout=5.0)
                except Exception:
                    pass
    except Exception:
        pass


# ─────────────────────────────────────────────
# v1.1.0 — CONFIDENCE SCORING ENGINE
# ─────────────────────────────────────────────

def compute_confidence(schema_id: str, validated_output: dict, schema_definition: dict) -> tuple[float, list[str]]:
    """
    After successful validation, score content reliability by comparing
    values against historical runs for the same schema.
    Returns (confidence_score 0.0-1.0, list of flagged field names).
    """
    if not validated_output or not schema_id:
        return 1.0, []

    try:
        with get_client() as client:
            resp = client.get("/validation_runs", params={
                "schema_id": f"eq.{schema_id}",
                "status": "in.(passed,corrected)",
                "select": "validated_output",
                "order": "created_at.desc",
                "limit": "200"
            })
            if resp.status_code != 200:
                return 1.0, []
            past_runs = resp.json()
    except Exception:
        return 1.0, []

    # Need at least 10 past runs for meaningful statistics
    valid_past = [r for r in past_runs if r.get("validated_output")]
    if len(valid_past) < 10:
        return 1.0, []

    properties = schema_definition.get("properties", {})
    if not properties:
        return 1.0, []

    confidence_flags = []

    for field, field_schema in properties.items():
        if field not in validated_output:
            continue

        value = validated_output[field]
        field_type = field_schema.get("type")

        # Collect past values for this field
        past_values = []
        for run in valid_past:
            out = run.get("validated_output")
            if out and field in out:
                past_values.append(out[field])

        if len(past_values) < 10:
            continue

        flagged = False

        if field_type in ("integer", "number") and isinstance(value, (int, float)):
            nums = [v for v in past_values if isinstance(v, (int, float))]
            if len(nums) >= 10:
                mean = statistics.mean(nums)
                try:
                    std = statistics.stdev(nums)
                    if std > 0 and abs(value - mean) > 3 * std:
                        flagged = True
                except statistics.StatisticsError:
                    pass

        elif field_type == "string" and isinstance(value, str):
            lengths = [len(v) for v in past_values if isinstance(v, str)]
            if len(lengths) >= 10:
                mean_len = statistics.mean(lengths)
                try:
                    std_len = statistics.stdev(lengths)
                    if std_len > 0 and abs(len(value) - mean_len) > 3 * std_len:
                        flagged = True
                except statistics.StatisticsError:
                    pass

        elif "enum" in field_schema:
            seen_values = {str(v) for v in past_values}
            if str(value) not in seen_values:
                flagged = True

        if flagged:
            confidence_flags.append(field)

    total_fields = len(properties)
    if total_fields == 0:
        return 1.0, []

    score = round(1.0 - (len(confidence_flags) / total_fields), 4)
    score = max(0.0, min(1.0, score))

    return score, confidence_flags


# ─────────────────────────────────────────────
# v1.2.0 — TAMPER-EVIDENT HASH CHAIN
# ─────────────────────────────────────────────

def compute_run_hash(run_id: str, schema_id: Optional[str], raw_ai_output: str,
                     status: str, validated_output: Any, created_at: str, previous_hash: str) -> str:
    """
    SHA-256 hash over canonical run data including the previous run's hash.
    Tampering with data OR chain link is detectable.
    """
    data = json.dumps({
        "run_id": str(run_id),
        "schema_id": str(schema_id) if schema_id else None,
        "raw_ai_output": raw_ai_output,
        "status": status,
        "validated_output": validated_output,
        "created_at": str(created_at),
        "previous_hash": previous_hash
    }, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


def get_previous_run_hash(schema_id: Optional[str]) -> str:
    """Get the most recent run_hash for this schema to chain against."""
    if not schema_id:
        return "GENESIS"
    try:
        with get_client() as client:
            resp = client.get("/validation_runs", params={
                "schema_id": f"eq.{schema_id}",
                "select": "run_hash",
                "order": "created_at.desc",
                "limit": "1"
            })
            if resp.status_code == 200:
                runs = resp.json()
                if runs and runs[0].get("run_hash"):
                    return runs[0]["run_hash"]
    except Exception:
        pass
    return "GENESIS"


# ─────────────────────────────────────────────
# CORE VALIDATION FLOW
# ─────────────────────────────────────────────

def run_validation(schema_id: str, ai_output: str, model_used: Optional[str], auto_correct: bool):
    start_time = datetime.now(timezone.utc)

    # Fetch schema
    with get_client() as client:
        resp = client.get("/schemas", params={"id": f"eq.{schema_id}"})
        if resp.status_code != 200 or not resp.json():
            raise HTTPException(status_code=404, detail="Schema not found")
        schema_row = resp.json()[0]

    schema_def = schema_row["schema_definition"]

    # Parse output
    try:
        parsed = json.loads(ai_output)
    except json.JSONDecodeError:
        parsed = None

    run_id = str(uuid.uuid4())
    status = "failed"
    validated_output = None
    reason = "Output is not valid JSON"
    attempts = 1
    auto_corrected = False
    confidence_score = None
    confidence_flags = []

    if parsed is not None:
        errors = validate_against_schema(parsed, schema_def)
        if not errors:
            status = "passed"
            validated_output = parsed
            reason = "Validation passed"
        else:
            reason = "; ".join(errors)

            if auto_correct:
                corrected_text = auto_correct_with_gemini(ai_output, reason, schema_def)
                if corrected_text:
                    attempts = 2
                    try:
                        corrected_parsed = json.loads(corrected_text)
                        corrected_errors = validate_against_schema(corrected_parsed, schema_def)
                        if not corrected_errors:
                            status = "corrected"
                            validated_output = corrected_parsed
                            reason = "Auto-corrected by Gemini"
                            auto_corrected = True
                    except json.JSONDecodeError:
                        pass

    # v1.1.0 — Confidence scoring on successful output
    if status in ("passed", "corrected") and validated_output:
        confidence_score, confidence_flags = compute_confidence(schema_id, validated_output, schema_def)

    latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
    created_at = datetime.now(timezone.utc).isoformat()

    # v1.2.0 — Compute hash chain
    previous_hash = get_previous_run_hash(schema_id)
    run_hash = compute_run_hash(
        run_id, schema_id, ai_output, status, validated_output, created_at, previous_hash
    )

    # Store run
    run_data = {
        "id": run_id,
        "schema_id": schema_id,
        "raw_ai_output": ai_output,
        "validated_output": validated_output,
        "status": status,
        "attempts": attempts,
        "latency_ms": latency_ms,
        "model_used": model_used,
        "confidence_score": confidence_score,
        "confidence_flags": confidence_flags if confidence_flags else None,
        "run_hash": run_hash,
        "previous_hash": previous_hash,
        "created_at": created_at
    }

    with get_client() as client:
        client.post("/validation_runs", json=run_data)

        # Log corrections
        if auto_corrected:
            client.post("/corrections", json={
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "attempt_number": 2,
                "failed_output": ai_output,
                "corrected_output": validated_output,
                "error_reason": reason
            })

    # Fire webhooks
    fire_webhooks(schema_id, run_id, status, reason, model_used, latency_ms)

    return {
        "run_id": run_id,
        "status": status,
        "passed": status in ("passed", "corrected"),
        "reason": reason,
        "data": validated_output,
        "auto_corrected": auto_corrected,
        "attempts": attempts,
        "latency_ms": latency_ms,
        "confidence_score": confidence_score,
        "confidence_flags": confidence_flags
    }


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "tool": "Iron-Thread",
        "version": "1.2.0",
        "status": "running",
        "description": "Open-source middleware that validates AI outputs before they reach your database.",
        "github": "https://github.com/eugene001dayne/iron-thread",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    try:
        start = datetime.now(timezone.utc)
        with get_client() as client:
            client.get("/schemas", params={"limit": "1"})
        db_latency = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        return {"status": "ok", "database": "connected", "db_latency_ms": db_latency}
    except Exception as e:
        return {"status": "degraded", "database": "error", "error": str(e)}


# ── SCHEMAS ──

@app.post("/schemas")
@limiter.limit("30/minute")
def create_schema(request: Request, body: SchemaCreate):
    schema_id = str(uuid.uuid4())
    row = {
        "id": schema_id,
        "name": body.name,
        "description": body.description,
        "schema_definition": body.schema_definition,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    with get_client() as client:
        resp = client.post("/schemas", json=row)
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Failed to create schema")
        return resp.json()[0] if resp.json() else row


@app.get("/schemas")
def list_schemas():
    with get_client() as client:
        resp = client.get("/schemas", params={"order": "created_at.desc"})
        return resp.json()


# ── VALIDATION ──

@app.post("/validate")
@limiter.limit("60/minute")
def validate_single(request: Request, body: ValidateRequest):
    return run_validation(body.schema_id, body.ai_output, body.model_used, body.auto_correct)


@app.post("/validate/batch")
@limiter.limit("20/minute")
def validate_batch(request: Request, body: BatchValidateRequest):
    results = []
    passed = 0
    failed = 0
    corrected = 0

    for output in body.ai_outputs:
        result = run_validation(body.schema_id, output, body.model_used, False)
        results.append(result)
        if result["status"] == "passed":
            passed += 1
        elif result["status"] == "corrected":
            corrected += 1
        else:
            failed += 1

    total = len(body.ai_outputs)
    success_rate = round(((passed + corrected) / total) * 100, 2) if total > 0 else 0.0

    return {
        "total": total,
        "passed": passed,
        "corrected": corrected,
        "failed": failed,
        "success_rate": success_rate,
        "results": results
    }


# ── RUNS ──

@app.get("/runs")
def list_runs():
    with get_client() as client:
        resp = client.get("/validation_runs", params={
            "order": "created_at.desc",
            "limit": "50"
        })
        return resp.json()


@app.get("/runs/export")
def export_runs():
    with get_client() as client:
        resp = client.get("/validation_runs", params={"order": "created_at.desc"})
        runs = resp.json()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "run_id", "schema_id", "status", "model_used",
        "latency_ms", "attempts", "confidence_score", "confidence_flags",
        "run_hash", "previous_hash", "created_at"
    ])
    for run in runs:
        writer.writerow([
            run.get("id"), run.get("schema_id"), run.get("status"),
            run.get("model_used"), run.get("latency_ms"), run.get("attempts"),
            run.get("confidence_score"),
            json.dumps(run.get("confidence_flags")) if run.get("confidence_flags") else "",
            run.get("run_hash", ""), run.get("previous_hash", ""),
            run.get("created_at")
        ])

    output.seek(0)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=iron_thread_runs_{timestamp}.csv"}
    )


# ── v1.2.0: RUN VERIFICATION ──

@app.get("/runs/{run_id}/verify")
def verify_run(run_id: str):
    with get_client() as client:
        resp = client.get("/validation_runs", params={"id": f"eq.{run_id}"})
        if resp.status_code != 200 or not resp.json():
            raise HTTPException(status_code=404, detail="Run not found")
        run = resp.json()[0]

    stored_hash = run.get("run_hash")
    if not stored_hash:
        return {
            "run_id": run_id,
            "verified": False,
            "reason": "Run predates tamper-evident logging (v1.2.0). No hash stored."
        }

    previous_hash = run.get("previous_hash", "GENESIS")
    recomputed = compute_run_hash(
        run["id"],
        run.get("schema_id"),
        run.get("raw_ai_output", ""),
        run.get("status", ""),
        run.get("validated_output"),
        run.get("created_at", ""),
        previous_hash
    )

    verified = recomputed == stored_hash
    return {
        "run_id": run_id,
        "verified": verified,
        "stored_hash": stored_hash,
        "recomputed_hash": recomputed,
        "previous_hash": previous_hash,
        "reason": "Hash matches — run data is intact." if verified else "Hash mismatch — run data may have been tampered with."
    }


# ── v1.2.0: SCHEMA CHAIN ──

@app.get("/schemas/{schema_id}/chain")
def get_schema_chain(schema_id: str):
    with get_client() as client:
        # Verify schema exists
        sr = client.get("/schemas", params={"id": f"eq.{schema_id}"})
        if not sr.json():
            raise HTTPException(status_code=404, detail="Schema not found")

        resp = client.get("/validation_runs", params={
            "schema_id": f"eq.{schema_id}",
            "select": "id,status,run_hash,previous_hash,created_at,raw_ai_output,validated_output,confidence_score",
            "order": "created_at.asc"
        })
        runs = resp.json()

    if not runs:
        return {
            "schema_id": schema_id,
            "total_runs": 0,
            "chain_verified": True,
            "runs": []
        }

    chain_entries = []
    chain_verified = True
    expected_previous = "GENESIS"

    for run in runs:
        stored_hash = run.get("run_hash")
        previous_hash = run.get("previous_hash")

        if not stored_hash:
            chain_entries.append({
                "run_id": run["id"],
                "status": run.get("status"),
                "created_at": run.get("created_at"),
                "run_hash": None,
                "previous_hash": None,
                "link_verified": None,
                "note": "Predates tamper-evident logging"
            })
            continue

        # Verify this link
        recomputed = compute_run_hash(
            run["id"],
            schema_id,
            run.get("raw_ai_output", ""),
            run.get("status", ""),
            run.get("validated_output"),
            run.get("created_at", ""),
            previous_hash
        )

        link_ok = (recomputed == stored_hash) and (previous_hash == expected_previous)
        if not link_ok:
            chain_verified = False

        chain_entries.append({
            "run_id": run["id"],
            "status": run.get("status"),
            "created_at": run.get("created_at"),
            "confidence_score": run.get("confidence_score"),
            "run_hash": stored_hash,
            "previous_hash": previous_hash,
            "link_verified": link_ok
        })

        expected_previous = stored_hash

    return {
        "schema_id": schema_id,
        "total_runs": len(runs),
        "chain_verified": chain_verified,
        "runs": chain_entries
    }


# ── DASHBOARD ──

@app.get("/dashboard/stats")
def dashboard_stats():
    with get_client() as client:
        resp = client.get("/validation_runs", params={"select": "status,latency_ms,confidence_score"})
        runs = resp.json()

    total = len(runs)
    passed = sum(1 for r in runs if r.get("status") == "passed")
    failed = sum(1 for r in runs if r.get("status") == "failed")
    corrected = sum(1 for r in runs if r.get("status") == "corrected")

    latencies = [r["latency_ms"] for r in runs if r.get("latency_ms") is not None]
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else 0

    success_rate = round(((passed + corrected) / total) * 100, 2) if total > 0 else 0.0

    confidence_scores = [r["confidence_score"] for r in runs if r.get("confidence_score") is not None]
    avg_confidence = round(sum(confidence_scores) / len(confidence_scores), 4) if confidence_scores else None

    return {
        "total_runs": total,
        "passed": passed,
        "failed": failed,
        "corrected": corrected,
        "success_rate": success_rate,
        "avg_latency_ms": avg_latency,
        "avg_confidence_score": avg_confidence
    }


# ── ANALYTICS ──

@app.get("/analytics/errors")
def analytics_errors():
    with get_client() as client:
        resp = client.get("/validation_runs", params={
            "status": "eq.failed",
            "select": "raw_ai_output,schema_id,created_at"
        })
        runs = resp.json()

    # Extract failure reasons by attempting to parse and validate
    # Since reason isn't stored separately, we return counts by schema
    schema_counts: dict = {}
    for run in runs:
        sid = run.get("schema_id", "unknown")
        schema_counts[sid] = schema_counts.get(sid, 0) + 1

    return {
        "total_failures": len(runs),
        "failures_by_schema": [{"schema_id": k, "count": v} for k, v in sorted(schema_counts.items(), key=lambda x: -x[1])]
    }


@app.get("/analytics/trends")
def analytics_trends():
    with get_client() as client:
        resp = client.get("/validation_runs", params={
            "select": "status,created_at",
            "order": "created_at.asc"
        })
        runs = resp.json()

    by_date: dict = {}
    for run in runs:
        date = run.get("created_at", "")[:10]
        if date not in by_date:
            by_date[date] = {"date": date, "total": 0, "passed": 0, "failed": 0, "corrected": 0}
        by_date[date]["total"] += 1
        status = run.get("status", "failed")
        if status in by_date[date]:
            by_date[date][status] += 1

    for d in by_date.values():
        d["success_rate"] = round(((d["passed"] + d["corrected"]) / d["total"]) * 100, 2) if d["total"] > 0 else 0.0

    return {"trends": list(by_date.values())}


@app.get("/analytics/models")
def analytics_models():
    with get_client() as client:
        resp = client.get("/validation_runs", params={
            "select": "status,latency_ms,model_used"
        })
        runs = resp.json()

    by_model: dict = {}
    for run in runs:
        model = run.get("model_used") or "unknown"
        if model not in by_model:
            by_model[model] = {"model": model, "total": 0, "passed": 0, "failed": 0, "corrected": 0, "latencies": []}
        by_model[model]["total"] += 1
        status = run.get("status", "failed")
        if status in ("passed", "failed", "corrected"):
            by_model[model][status] += 1
        if run.get("latency_ms") is not None:
            by_model[model]["latencies"].append(run["latency_ms"])

    results = []
    for m in by_model.values():
        lats = m.pop("latencies")
        total = m["total"]
        m["success_rate"] = round(((m["passed"] + m["corrected"]) / total) * 100, 2) if total > 0 else 0.0
        m["avg_latency_ms"] = round(sum(lats) / len(lats)) if lats else 0
        results.append(m)

    return {"models": sorted(results, key=lambda x: -x["total"])}


@app.get("/analytics/schemas")
def analytics_schemas():
    with get_client() as client:
        resp = client.get("/validation_runs", params={
            "select": "status,schema_id,latency_ms,confidence_score"
        })
        runs = resp.json()

        schemas_resp = client.get("/schemas", params={"select": "id,name"})
        schema_names = {s["id"]: s["name"] for s in schemas_resp.json()}

    by_schema: dict = {}
    for run in runs:
        sid = run.get("schema_id") or "unknown"
        if sid not in by_schema:
            by_schema[sid] = {
                "schema_id": sid,
                "schema_name": schema_names.get(sid, "unknown"),
                "total": 0, "passed": 0, "failed": 0, "corrected": 0,
                "latencies": [], "confidence_scores": []
            }
        by_schema[sid]["total"] += 1
        status = run.get("status", "failed")
        if status in ("passed", "failed", "corrected"):
            by_schema[sid][status] += 1
        if run.get("latency_ms") is not None:
            by_schema[sid]["latencies"].append(run["latency_ms"])
        if run.get("confidence_score") is not None:
            by_schema[sid]["confidence_scores"].append(run["confidence_score"])

    results = []
    for s in by_schema.values():
        lats = s.pop("latencies")
        scores = s.pop("confidence_scores")
        total = s["total"]
        s["success_rate"] = round(((s["passed"] + s["corrected"]) / total) * 100, 2) if total > 0 else 0.0
        s["avg_latency_ms"] = round(sum(lats) / len(lats)) if lats else 0
        s["avg_confidence_score"] = round(sum(scores) / len(scores), 4) if scores else None
        results.append(s)

    return {"schemas": sorted(results, key=lambda x: x["success_rate"])}


# ── WEBHOOKS ──

@app.post("/webhooks")
def create_webhook(body: WebhookCreate):
    row = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "url": body.url,
        "on_failure": body.on_failure,
        "on_success": body.on_success,
        "schema_id": body.schema_id,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    with get_client() as client:
        resp = client.post("/webhooks", json=row)
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Failed to create webhook")
        return resp.json()[0] if resp.json() else row


@app.get("/webhooks")
def list_webhooks():
    with get_client() as client:
        resp = client.get("/webhooks", params={"order": "created_at.desc"})
        return resp.json()


@app.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str):
    with get_client() as client:
        client.patch(
            "/webhooks",
            params={"id": f"eq.{webhook_id}"},
            json={"active": False}
        )
    return {"deleted": True, "webhook_id": webhook_id}