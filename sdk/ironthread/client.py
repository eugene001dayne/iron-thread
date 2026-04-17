import httpx
import json
from typing import Optional, Any

RENDER_URL = "https://iron-thread.onrender.com"


class ValidationResult:
    def __init__(self, data: dict):
        self.run_id: str = data.get("run_id", "")
        self.status: str = data.get("status", "")
        self.passed: bool = data.get("passed", False)
        self.reason: str = data.get("reason", "")
        self.data: Any = data.get("data")
        self.auto_corrected: bool = data.get("auto_corrected", False)
        self.attempts: int = data.get("attempts", 1)
        self.latency_ms: Optional[int] = data.get("latency_ms")
        self.confidence_score: Optional[float] = data.get("confidence_score")
        self.confidence_flags: list = data.get("confidence_flags", [])
        self._raw = data

    def __repr__(self):
        return f"ValidationResult(status={self.status}, passed={self.passed}, confidence={self.confidence_score})"


class BatchValidationResult:
    def __init__(self, data: dict):
        self.total: int = data.get("total", 0)
        self.passed: int = data.get("passed", 0)
        self.corrected: int = data.get("corrected", 0)
        self.failed: int = data.get("failed", 0)
        self.success_rate: float = data.get("success_rate", 0.0)
        self.results: list[ValidationResult] = [ValidationResult(r) for r in data.get("results", [])]
        self._raw = data

    def __repr__(self):
        return f"BatchValidationResult(total={self.total}, passed={self.passed}, failed={self.failed}, success_rate={self.success_rate}%)"


class IronThread:
    def __init__(self, base_url: str = RENDER_URL):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)

    # ── SCHEMAS ──

    def create_schema(self, name: str, schema_definition: dict, description: str = None) -> dict:
        resp = self._client.post("/schemas", json={
            "name": name,
            "schema_definition": schema_definition,
            "description": description
        })
        resp.raise_for_status()
        return resp.json()

    def list_schemas(self) -> list:
        resp = self._client.get("/schemas")
        resp.raise_for_status()
        return resp.json()

    # ── VALIDATION ──

    def validate(self, ai_output: str, schema_id: str, model_used: str = None,
                 auto_correct: bool = False) -> ValidationResult:
        resp = self._client.post("/validate", json={
            "ai_output": ai_output,
            "schema_id": schema_id,
            "model_used": model_used,
            "auto_correct": auto_correct
        })
        resp.raise_for_status()
        return ValidationResult(resp.json())

    def validate_batch(self, ai_outputs: list[str], schema_id: str,
                       model_used: str = None) -> BatchValidationResult:
        resp = self._client.post("/validate/batch", json={
            "ai_outputs": ai_outputs,
            "schema_id": schema_id,
            "model_used": model_used
        })
        resp.raise_for_status()
        return BatchValidationResult(resp.json())

    # ── RUNS ──

    def runs(self) -> list:
        resp = self._client.get("/runs")
        resp.raise_for_status()
        return resp.json()

    def export_csv(self, filename: str = "iron_thread_runs.csv") -> str:
        resp = self._client.get("/runs/export")
        resp.raise_for_status()
        with open(filename, "w") as f:
            f.write(resp.text)
        return filename

    # ── v1.2.0: TAMPER-EVIDENT VERIFICATION ──

    def verify_run(self, run_id: str) -> dict:
        """Verify the SHA-256 hash of a single validation run is intact."""
        resp = self._client.get(f"/runs/{run_id}/verify")
        resp.raise_for_status()
        return resp.json()

    def get_schema_chain(self, schema_id: str) -> dict:
        """Get the full tamper-evident hash chain for a schema."""
        resp = self._client.get(f"/schemas/{schema_id}/chain")
        resp.raise_for_status()
        return resp.json()

    # ── ANALYTICS ──

    def stats(self) -> dict:
        resp = self._client.get("/dashboard/stats")
        resp.raise_for_status()
        return resp.json()

    def analytics_errors(self) -> dict:
        resp = self._client.get("/analytics/errors")
        resp.raise_for_status()
        return resp.json()

    def analytics_trends(self) -> dict:
        resp = self._client.get("/analytics/trends")
        resp.raise_for_status()
        return resp.json()

    def analytics_models(self) -> dict:
        resp = self._client.get("/analytics/models")
        resp.raise_for_status()
        return resp.json()

    def analytics_schemas(self) -> dict:
        resp = self._client.get("/analytics/schemas")
        resp.raise_for_status()
        return resp.json()

    # ── WEBHOOKS ──

    def create_webhook(self, name: str, url: str, on_failure: bool = True,
                       on_success: bool = False, schema_id: str = None) -> dict:
        resp = self._client.post("/webhooks", json={
            "name": name,
            "url": url,
            "on_failure": on_failure,
            "on_success": on_success,
            "schema_id": schema_id
        })
        resp.raise_for_status()
        return resp.json()

    def list_webhooks(self) -> list:
        resp = self._client.get("/webhooks")
        resp.raise_for_status()
        return resp.json()

    def delete_webhook(self, webhook_id: str) -> dict:
        resp = self._client.delete(f"/webhooks/{webhook_id}")
        resp.raise_for_status()
        return resp.json()

    def health(self) -> dict:
        resp = self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    def __repr__(self):
        return f"IronThread(base_url={self.base_url})"