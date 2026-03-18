from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional
import httpx
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Iron-Thread", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# --- Models ---
class SchemaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    schema_definition: dict

class ValidateRequest(BaseModel):
    schema_id: str
    ai_output: str
    model_used: Optional[str] = "unknown"

# --- Supabase helpers ---
async def db_insert(table: str, data: dict):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={**HEADERS, "Prefer": "return=representation"},
            json=data
        )
        return r.json()

async def db_select(table: str, filters: str = ""):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{table}{filters}",
            headers=HEADERS
        )
        return r.json()

async def db_update(table: str, record_id: str, data: dict):
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{record_id}",
            headers={**HEADERS, "Prefer": "return=representation"},
            json=data
        )
        return r.json()

# --- Validation logic ---
def validate_against_schema(output: str, schema: dict) -> tuple[bool, Any, str]:
    try:
        parsed = json.loads(output)
        required_keys = schema.get("required", [])
        for key in required_keys:
            if key not in parsed:
                return False, None, f"Missing required field: {key}"
        properties = schema.get("properties", {})
        for key, rules in properties.items():
            if key in parsed:
                expected_type = rules.get("type")
                value = parsed[key]
                type_map = {
                    "string": str, "integer": int,
                    "number": (int, float), "boolean": bool,
                    "array": list, "object": dict
                }
                if expected_type and not isinstance(value, type_map.get(expected_type, object)):
                    return False, None, f"Field '{key}' expected {expected_type}"
        return True, parsed, "OK"
    except json.JSONDecodeError as e:
        return False, None, f"Invalid JSON: {str(e)}"

# --- Routes ---
@app.get("/")
def root():
    return {"status": "Iron-Thread is running", "version": "0.1.0"}

@app.post("/schemas")
async def create_schema(body: SchemaCreate):
    result = await db_insert("schemas", {
        "name": body.name,
        "description": body.description,
        "schema_definition": body.schema_definition
    })
    return result

@app.get("/schemas")
async def list_schemas():
    return await db_select("schemas")

@app.post("/validate")
async def validate(body: ValidateRequest):
    start = time.time()

    schemas = await db_select("schemas", f"?id=eq.{body.schema_id}")
    if not schemas:
        raise HTTPException(status_code=404, detail="Schema not found")

    schema_def = schemas[0]["schema_definition"]
    is_valid, parsed, reason = validate_against_schema(body.ai_output, schema_def)
    latency = int((time.time() - start) * 1000)

    status = "passed" if is_valid else "failed"

    run = await db_insert("validation_runs", {
        "schema_id": body.schema_id,
        "raw_ai_output": body.ai_output,
        "validated_output": parsed,
        "status": status,
        "attempts": 1,
        "latency_ms": latency,
        "model_used": body.model_used
    })

    return {
        "status": status,
        "reason": reason,
        "validated_output": parsed,
        "latency_ms": latency,
        "run_id": run[0]["id"] if run else None
    }

@app.get("/dashboard/stats")
async def dashboard_stats():
    runs = await db_select("validation_runs")
    if not runs:
        return {
            "total_runs": 0, "passed": 0,
            "failed": 0, "corrected": 0,
            "success_rate": 0, "avg_latency_ms": 0
        }
    total = len(runs)
    passed = sum(1 for r in runs if r["status"] == "passed")
    failed = sum(1 for r in runs if r["status"] == "failed")
    corrected = sum(1 for r in runs if r["status"] == "corrected")
    avg_latency = int(sum(r["latency_ms"] or 0 for r in runs) / total)
    success_rate = round(100 * (passed + corrected) / total, 2)
    return {
        "total_runs": total,
        "passed": passed,
        "failed": failed,
        "corrected": corrected,
        "success_rate": success_rate,
        "avg_latency_ms": avg_latency
    }

@app.get("/runs")
async def list_runs():
    return await db_select("validation_runs", "?order=created_at.desc&limit=50")

@app.get("/analytics/errors")
async def error_patterns():
    runs = await db_select("validation_runs", "?status=eq.failed&order=created_at.desc")
    if not runs:
        return {"patterns": [], "total_failures": 0}
    
    # Count error patterns
    error_counts = {}
    for run in runs:
        # Get corrections for this run
        corrections = await db_select("corrections", f"?run_id=eq.{run['id']}")
        for correction in corrections:
            reason = correction.get("error_reason", "Unknown error")
            error_counts[reason] = error_counts.get(reason, 0) + 1
    
    # Also count from validation_runs directly
    all_failed = await db_select("validation_runs", "?status=eq.failed")
    for run in all_failed:
        # Extract error from raw output patterns
        raw = run.get("raw_ai_output", "")
        if not raw:
            continue
        try:
            json.loads(raw)
        except json.JSONDecodeError:
            reason = "Invalid JSON"
            error_counts[reason] = error_counts.get(reason, 0) + 1

    patterns = [
        {"reason": k, "count": v, "percentage": round(100 * v / len(all_failed), 2)}
        for k, v in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "total_failures": len(all_failed),
        "patterns": patterns
    }


@app.get("/analytics/trends")
async def trends():
    runs = await db_select("validation_runs", "?order=created_at.asc")
    if not runs:
        return {"trends": []}

    # Group by date
    from collections import defaultdict
    daily = defaultdict(lambda: {"passed": 0, "failed": 0, "corrected": 0, "total": 0})

    for run in runs:
        date = run["created_at"][:10]  # YYYY-MM-DD
        daily[date]["total"] += 1
        daily[date][run["status"]] += 1

    trends = []
    for date, stats in sorted(daily.items()):
        success_rate = round(100 * (stats["passed"] + stats["corrected"]) / stats["total"], 2)
        trends.append({
            "date": date,
            "total": stats["total"],
            "passed": stats["passed"],
            "failed": stats["failed"],
            "corrected": stats["corrected"],
            "success_rate": success_rate
        })

    return {"trends": trends}


@app.get("/analytics/models")
async def model_performance():
    runs = await db_select("validation_runs", "?order=created_at.desc")
    if not runs:
        return {"models": []}

    from collections import defaultdict
    model_stats = defaultdict(lambda: {"passed": 0, "failed": 0, "corrected": 0, "total": 0, "latencies": []})

    for run in runs:
        model = run.get("model_used") or "unknown"
        model_stats[model]["total"] += 1
        model_stats[model][run["status"]] += 1
        if run.get("latency_ms"):
            model_stats[model]["latencies"].append(run["latency_ms"])

    models = []
    for model, stats in model_stats.items():
        avg_latency = int(sum(stats["latencies"]) / len(stats["latencies"])) if stats["latencies"] else 0
        success_rate = round(100 * (stats["passed"] + stats["corrected"]) / stats["total"], 2)
        models.append({
            "model": model,
            "total": stats["total"],
            "passed": stats["passed"],
            "failed": stats["failed"],
            "corrected": stats["corrected"],
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency
        })

    return {"models": sorted(models, key=lambda x: x["total"], reverse=True)}


@app.get("/analytics/schemas")
async def schema_performance():
    runs = await db_select("validation_runs", "?order=created_at.desc")
    schemas = await db_select("schemas")
    if not runs or not schemas:
        return {"schemas": []}

    schema_map = {s["id"]: s["name"] for s in schemas}

    from collections import defaultdict
    schema_stats = defaultdict(lambda: {"passed": 0, "failed": 0, "corrected": 0, "total": 0})

    for run in runs:
        sid = run.get("schema_id")
        if sid:
            schema_stats[sid]["total"] += 1
            schema_stats[sid][run["status"]] += 1

    result = []
    for sid, stats in schema_stats.items():
        success_rate = round(100 * (stats["passed"] + stats["corrected"]) / stats["total"], 2)
        result.append({
            "schema_id": sid,
            "schema_name": schema_map.get(sid, "Unknown"),
            "total": stats["total"],
            "passed": stats["passed"],
            "failed": stats["failed"],
            "corrected": stats["corrected"],
            "success_rate": success_rate
        })

    return {"schemas": sorted(result, key=lambda x: x["total"], reverse=True)}