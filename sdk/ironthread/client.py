import httpx
import json
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    passed: bool
    status: str
    reason: str
    data: Any
    latency_ms: int
    run_id: Optional[str] = None


class IronThread:
    def __init__(self, host: str = "https://iron-thread-production.up.railway.app"):
        self.host = host.rstrip("/")

    def create_schema(self, name: str, schema_definition: dict, description: str = "") -> dict:
        with httpx.Client() as client:
            r = client.post(
                f"{self.host}/schemas",
                json={
                    "name": name,
                    "description": description,
                    "schema_definition": schema_definition
                }
            )
            return r.json()[0]

    def list_schemas(self) -> list:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/schemas")
            return r.json()

    def validate(self, ai_output: Any, schema_id: str, model_used: str = "unknown") -> ValidationResult:
        if not isinstance(ai_output, str):
            ai_output = json.dumps(ai_output)

        with httpx.Client() as client:
            r = client.post(
                f"{self.host}/validate",
                json={
                    "schema_id": schema_id,
                    "ai_output": ai_output,
                    "model_used": model_used
                }
            )
            data = r.json()

        return ValidationResult(
            passed=data["status"] == "passed",
            status=data["status"],
            reason=data["reason"],
            data=data["validated_output"],
            latency_ms=data["latency_ms"],
            run_id=data.get("run_id")
        )

    def stats(self) -> dict:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/dashboard/stats")
            return r.json()

    def runs(self) -> list:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/runs")
            return r.json()


# Convenience function for quick use
_default_client = IronThread()

def validate(ai_output: Any, schema_id: str, model_used: str = "unknown") -> ValidationResult:
    return _default_client.validate(ai_output, schema_id, model_used)