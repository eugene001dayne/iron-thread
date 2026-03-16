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