const fetch = require("node-fetch");

const RENDER_URL = "https://iron-thread.onrender.com";

class IronThread {
  constructor(baseUrl = RENDER_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  async _request(method, path, body = null) {
    const options = {
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (body) options.body = JSON.stringify(body);
    const res = await fetch(`${this.baseUrl}${path}`, options);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`IronThread error ${res.status}: ${text}`);
    }
    return res.json();
  }

  // ── SCHEMAS ──

  createSchema(name, schemaDefinition, description = null) {
    return this._request("POST", "/schemas", {
      name,
      schema_definition: schemaDefinition,
      description,
    });
  }

  listSchemas() {
    return this._request("GET", "/schemas");
  }

  // ── VALIDATION ──

  validate(aiOutput, schemaId, modelUsed = null, autoCorrect = false) {
    return this._request("POST", "/validate", {
      ai_output: aiOutput,
      schema_id: schemaId,
      model_used: modelUsed,
      auto_correct: autoCorrect,
    });
  }

  validateBatch(aiOutputs, schemaId, modelUsed = null) {
    return this._request("POST", "/validate/batch", {
      ai_outputs: aiOutputs,
      schema_id: schemaId,
      model_used: modelUsed,
    });
  }

  // ── RUNS ──

  runs() {
    return this._request("GET", "/runs");
  }

  // ── v1.2.0: TAMPER-EVIDENT VERIFICATION ──

  verifyRun(runId) {
    return this._request("GET", `/runs/${runId}/verify`);
  }

  getSchemaChain(schemaId) {
    return this._request("GET", `/schemas/${schemaId}/chain`);
  }

  // ── ANALYTICS ──

  stats() {
    return this._request("GET", "/dashboard/stats");
  }

  analyticsErrors() {
    return this._request("GET", "/analytics/errors");
  }

  analyticsTrends() {
    return this._request("GET", "/analytics/trends");
  }

  analyticsModels() {
    return this._request("GET", "/analytics/models");
  }

  analyticsSchemas() {
    return this._request("GET", "/analytics/schemas");
  }

  // ── WEBHOOKS ──

  createWebhook(name, url, onFailure = true, onSuccess = false, schemaId = null) {
    return this._request("POST", "/webhooks", {
      name,
      url,
      on_failure: onFailure,
      on_success: onSuccess,
      schema_id: schemaId,
    });
  }

  listWebhooks() {
    return this._request("GET", "/webhooks");
  }

  deleteWebhook(webhookId) {
    return this._request("DELETE", `/webhooks/${webhookId}`);
  }

  health() {
    return this._request("GET", "/health");
  }
}

module.exports = { IronThread };