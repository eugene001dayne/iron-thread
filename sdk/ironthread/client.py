import httpx
import json
from typing import Any, Optional, List
from dataclasses import dataclass


@dataclass
class ValidationResult:
    passed: bool
    status: str
    reason: str
    data: Any
    latency_ms: int
    run_id: Optional[str] = None


@dataclass
class BatchValidationResult:
    total: int
    passed: int
    failed: int
    success_rate: float
    results: List[ValidationResult]


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

    def validate_batch(self, ai_outputs: List[Any], schema_id: str, model_used: str = "unknown") -> BatchValidationResult:
        outputs = [json.dumps(o) if not isinstance(o, str) else o for o in ai_outputs]

        with httpx.Client() as client:
            r = client.post(
                f"{self.host}/validate/batch",
                json={
                    "schema_id": schema_id,
                    "ai_outputs": outputs,
                    "model_used": model_used
                }
            )
            data = r.json()

        results = [
            ValidationResult(
                passed=r["status"] == "passed",
                status=r["status"],
                reason=r["reason"],
                data=r["validated_output"],
                latency_ms=r["latency_ms"],
                run_id=r.get("run_id")
            )
            for r in data["results"]
        ]

        return BatchValidationResult(
            total=data["total"],
            passed=data["passed"],
            failed=data["failed"],
            success_rate=data["success_rate"],
            results=results
        )

    def create_webhook(self, name: str, url: str, on_failure: bool = True, on_success: bool = False, schema_id: str = None) -> dict:
        with httpx.Client() as client:
            r = client.post(
                f"{self.host}/webhooks",
                json={
                    "name": name,
                    "url": url,
                    "on_failure": on_failure,
                    "on_success": on_success,
                    "schema_id": schema_id
                }
            )
            return r.json()[0]

    def list_webhooks(self) -> list:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/webhooks")
            return r.json()

    def delete_webhook(self, webhook_id: str) -> dict:
        with httpx.Client() as client:
            r = client.delete(f"{self.host}/webhooks/{webhook_id}")
            return r.json()

    def stats(self) -> dict:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/dashboard/stats")
            return r.json()

    def runs(self) -> list:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/runs")
            return r.json()

    def health(self) -> dict:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/health")
            return r.json()

    def export_csv(self, filepath: str = "iron-thread-runs.csv") -> str:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/runs/export")
            with open(filepath, "w") as f:
                f.write(r.text)
        return filepath

    def analytics_trends(self) -> dict:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/analytics/trends")
            return r.json()

    def analytics_models(self) -> dict:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/analytics/models")
            return r.json()

    def analytics_schemas(self) -> dict:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/analytics/schemas")
            return r.json()

    def analytics_errors(self) -> dict:
        with httpx.Client() as client:
            r = client.get(f"{self.host}/analytics/errors")
            return r.json()


# Convenience function for quick use
_default_client = IronThread()


def validate(ai_output: Any, schema_id: str, model_used: str = "unknown") -> ValidationResult:
    return _default_client.validate(ai_output, schema_id, model_used)


def validate_batch(ai_outputs: List[Any], schema_id: str, model_used: str = "unknown") -> BatchValidationResult:
    return _default_client.validate_batch(ai_outputs, schema_id, model_used)