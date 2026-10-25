"""Iron-Thread Python client."""
import json
import os
from typing import Any, Optional

import httpx

from .verify import VerifyResult, verify_chain

DEFAULT_URL = "http://localhost:8000"


class IronThreadError(httpx.HTTPStatusError):
    """
    The server answered with an error. It is an httpx.HTTPStatusError, so existing
    `except httpx.HTTPStatusError` code keeps working, but it also carries the server's own explanation.

    status_code -- the HTTP status
    detail      -- the server's message, e.g. how to configure an API key
    """

    def __init__(self, response: httpx.Response):
        self.status_code = response.status_code
        self.detail = _detail(response)
        super().__init__(
            f"Iron-Thread server answered {self.status_code}: {self.detail}",
            request=response.request,
            response=response,
        )


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict) and "detail" in body:
            detail = body["detail"]
            return detail if isinstance(detail, str) else json.dumps(detail)
    except ValueError:
        pass
    return response.text[:300]


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
        # The signed receipt for this verdict (None if the server could not sign; see attestation_error).
        self.attestation: Optional[dict] = data.get("attestation")
        self.attestation_error: Optional[str] = data.get("attestation_error")
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
        self.results: list = [ValidationResult(r) for r in data.get("results", [])]
        self._raw = data

    def __repr__(self):
        return (f"BatchValidationResult(total={self.total}, passed={self.passed}, "
                f"failed={self.failed}, success_rate={self.success_rate}%)")


class IronThread:
    """
    Client for an Iron-Thread server.

        it = IronThread()                                    # http://localhost:8000
        it = IronThread("https://my-server", api_key="...")  # a server that uses API keys

    base_url defaults to $IRONTHREAD_URL, then http://localhost:8000.
    api_key defaults to $IRONTHREAD_API_KEY. Pass `client=` to supply your own httpx.Client.
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 timeout: float = 30.0, client: Optional[httpx.Client] = None):
        self.base_url = (base_url or os.getenv("IRONTHREAD_URL") or DEFAULT_URL).rstrip("/")
        key = api_key or os.getenv("IRONTHREAD_API_KEY")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout, headers=headers)

    # ── plumbing ──

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.ConnectError as e:
            raise httpx.ConnectError(
                f"Cannot reach Iron-Thread at {self.base_url}. "
                "Is the server running? Start it with: python -m uvicorn main:app"
            ) from e
        if resp.status_code >= 400:
            raise IronThreadError(resp)
        return resp

    def _json(self, method: str, path: str, **kwargs) -> Any:
        return self._request(method, path, **kwargs).json()

    # ── SCHEMAS ──

    def create_schema(self, name: str, schema_definition: dict, description: Optional[str] = None) -> dict:
        return self._json("POST", "/schemas", json={
            "name": name, "schema_definition": schema_definition, "description": description})

    def list_schemas(self) -> list:
        return self._json("GET", "/schemas")

    # ── VALIDATION ──

    def validate(self, ai_output, schema_id: str, model_used: Optional[str] = None,
                 auto_correct: bool = False) -> ValidationResult:
        """Check an AI output (a JSON string, or a dict/list that is serialised for you)."""
        if not isinstance(ai_output, str):
            ai_output = json.dumps(ai_output)
        return ValidationResult(self._json("POST", "/validate", json={
            "ai_output": ai_output, "schema_id": schema_id,
            "model_used": model_used, "auto_correct": auto_correct}))

    def validate_batch(self, ai_outputs: list, schema_id: str,
                       model_used: Optional[str] = None) -> BatchValidationResult:
        outputs = [o if isinstance(o, str) else json.dumps(o) for o in ai_outputs]
        return BatchValidationResult(self._json("POST", "/validate/batch", json={
            "ai_outputs": outputs, "schema_id": schema_id, "model_used": model_used}))

    # ── RUNS ──

    def runs(self) -> list:
        return self._json("GET", "/runs")

    def export_csv(self, filename: str = "iron_thread_runs.csv") -> str:
        text = self._request("GET", "/runs/export").text
        with open(filename, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return filename

    # ── RECEIPTS: signed, hash-chained attestations ──

    def public_keys(self) -> list:
        """The server's public signing keys: [{"key_id": ..., "public_key": <base64>}]."""
        return self._json("GET", "/attestations/keys")["keys"]

    def get_attestation(self, run_id: str) -> dict:
        """The receipt for one run."""
        return self._json("GET", f"/attestations/runs/{run_id}")

    def get_chain(self, schema_id: str) -> list:
        """Every receipt for a schema, oldest first, ready for offline verification."""
        return self._json("GET", f"/attestations/chains/{schema_id}")["entries"]

    def verify_chain_remote(self, schema_id: str) -> dict:
        """Ask the SERVER whether a chain is intact. You are trusting its answer; see verify_chain_offline."""
        return self._json("GET", f"/attestations/chains/{schema_id}/verify")

    def verify_chain_offline(self, schema_id: str, public_key: str, expect_head: Optional[str] = None,
                             expect_length: Optional[int] = None) -> VerifyResult:
        """
        Fetch a chain and check it yourself, here, with a public key you trust (not one fetched
        from the same server). Needs: pip install "iron-thread[verify]".
        Pass expect_head / expect_length, recorded earlier, to catch a truncated or rewritten chain.
        """
        return verify_chain(self.get_chain(schema_id), public_key, expect_head, expect_length)

    def verify_attestation(self, entry: dict, input: Optional[str] = None, output: Any = None,
                           schema_definition: Optional[dict] = None) -> dict:
        """Stateless check of one receipt, optionally against the original input, output and schema."""
        body: dict = {"entry": entry}
        if input is not None:
            body["input"] = input
        if output is not None:
            body["output"] = output
        if schema_definition is not None:
            body["schema_definition"] = schema_definition
        return self._json("POST", "/attestations/verify", json=body)

    def reconcile(self, schema_id: str) -> dict:
        """Do the stored runs still match what was signed? Also reports runs with no receipt."""
        return self._json("GET", f"/attestations/chains/{schema_id}/reconcile")

    # ── legacy: the older unsigned hash chain (prefer the receipts above) ──

    def verify_run(self, run_id: str) -> dict:
        return self._json("GET", f"/runs/{run_id}/verify")

    def get_schema_chain(self, schema_id: str) -> dict:
        return self._json("GET", f"/schemas/{schema_id}/chain")

    # ── ANALYTICS ──

    def stats(self) -> dict:
        return self._json("GET", "/dashboard/stats")

    def analytics_errors(self) -> dict:
        return self._json("GET", "/analytics/errors")

    def analytics_trends(self) -> dict:
        return self._json("GET", "/analytics/trends")

    def analytics_models(self) -> dict:
        return self._json("GET", "/analytics/models")

    def analytics_schemas(self) -> dict:
        return self._json("GET", "/analytics/schemas")

    # ── WEBHOOKS ──

    def create_webhook(self, name: str, url: str, on_failure: bool = True,
                       on_success: bool = False, schema_id: Optional[str] = None) -> dict:
        return self._json("POST", "/webhooks", json={
            "name": name, "url": url, "on_failure": on_failure,
            "on_success": on_success, "schema_id": schema_id})

    def list_webhooks(self) -> list:
        return self._json("GET", "/webhooks")

    def delete_webhook(self, webhook_id: str) -> dict:
        return self._json("DELETE", f"/webhooks/{webhook_id}")

    def health(self) -> dict:
        return self._json("GET", "/health")

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __repr__(self):
        return f"IronThread(base_url={self.base_url})"
