"use strict";
const { verifyChain, canonical } = require("./verify");

const DEFAULT_URL = "http://localhost:8000";

/** The server answered with an error (status 0 means it could not be reached at all). */
class IronThreadError extends Error {
  constructor(status, detail, url) {
    super(`Iron-Thread server answered ${status}: ${detail}`);
    this.name = "IronThreadError";
    this.status = status;
    this.detail = detail;
    this.url = url;
  }
}

function detailOf(text) {
  try {
    const parsed = JSON.parse(text);
    if (parsed && parsed.detail !== undefined) {
      return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    }
  } catch {
    // not JSON: fall through to the raw text
  }
  return text.slice(0, 300);
}

class IronThread {
  /**
   * new IronThread()                                    // http://localhost:8000
   * new IronThread("https://my-server", { apiKey })     // a server that uses API keys
   * new IronThread({ baseUrl, apiKey, timeoutMs })
   * baseUrl defaults to $IRONTHREAD_URL, apiKey to $IRONTHREAD_API_KEY.
   */
  constructor(baseUrl, options = {}) {
    if (baseUrl !== null && typeof baseUrl === "object") {
      options = baseUrl;
      baseUrl = options.baseUrl;
    }
    const env = typeof process !== "undefined" && process.env ? process.env : {};
    this.baseUrl = String(baseUrl || env.IRONTHREAD_URL || DEFAULT_URL).replace(/\/+$/, "");
    this.apiKey = options.apiKey || env.IRONTHREAD_API_KEY || null;
    this.timeoutMs = options.timeoutMs === undefined ? 30000 : options.timeoutMs;
    this._fetch = options.fetch || globalThis.fetch;
  }

  async _request(method, path, body = null, { text = false } = {}) {
    const url = `${this.baseUrl}${path}`;
    const headers = { Accept: "application/json" };
    if (body !== null) headers["Content-Type"] = "application/json";
    if (this.apiKey) headers.Authorization = `Bearer ${this.apiKey}`;

    let res;
    try {
      res = await this._fetch(url, {
        method,
        headers,
        body: body !== null ? JSON.stringify(body) : undefined,
        signal: this.timeoutMs ? AbortSignal.timeout(this.timeoutMs) : undefined,
      });
    } catch (cause) {
      const err = new IronThreadError(
        0,
        `cannot reach Iron-Thread at ${this.baseUrl}. Is the server running? Start it with: python -m uvicorn main:app`,
        url
      );
      err.cause = cause;
      throw err;
    }
    const payload = await res.text();
    if (!res.ok) throw new IronThreadError(res.status, detailOf(payload), url);
    return text ? payload : JSON.parse(payload);
  }

  // ── SCHEMAS ──

  createSchema(name, schemaDefinition, description = null) {
    return this._request("POST", "/schemas", { name, schema_definition: schemaDefinition, description });
  }

  listSchemas() {
    return this._request("GET", "/schemas");
  }

  // ── VALIDATION ──

  /** aiOutput may be a JSON string, or an object/array that is serialised for you. */
  validate(aiOutput, schemaId, modelUsed = null, autoCorrect = false) {
    return this._request("POST", "/validate", {
      ai_output: typeof aiOutput === "string" ? aiOutput : JSON.stringify(aiOutput),
      schema_id: schemaId,
      model_used: modelUsed,
      auto_correct: autoCorrect,
    });
  }

  validateBatch(aiOutputs, schemaId, modelUsed = null) {
    return this._request("POST", "/validate/batch", {
      ai_outputs: aiOutputs.map((o) => (typeof o === "string" ? o : JSON.stringify(o))),
      schema_id: schemaId,
      model_used: modelUsed,
    });
  }

  // ── RUNS ──

  runs() {
    return this._request("GET", "/runs");
  }

  /** The runs as CSV text. */
  exportRuns() {
    return this._request("GET", "/runs/export", null, { text: true });
  }

  // ── RECEIPTS: signed, hash-chained attestations ──

  /** The server's public signing keys: [{ key_id, public_key }]. */
  async publicKeys() {
    return (await this._request("GET", "/attestations/keys")).keys;
  }

  getAttestation(runId) {
    return this._request("GET", `/attestations/runs/${runId}`);
  }

  /** Every receipt for a schema, oldest first, ready for offline verification. */
  async getChain(schemaId) {
    return (await this._request("GET", `/attestations/chains/${schemaId}`)).entries;
  }

  /** Ask the SERVER whether a chain is intact. You are trusting its answer; see verifyChainOffline. */
  verifyChainRemote(schemaId) {
    return this._request("GET", `/attestations/chains/${schemaId}/verify`);
  }

  /**
   * Fetch a chain and check it yourself, here, with a public key you trust (not one fetched from the same
   * server). Pass expectHead / expectLength, recorded earlier, to catch a truncated or rewritten chain.
   */
  async verifyChainOffline(schemaId, publicKey, options = {}) {
    return verifyChain(await this.getChain(schemaId), publicKey, options);
  }

  /** Stateless check of one receipt, optionally against the original input, output and schema. */
  verifyAttestation(entry, { input, output, schemaDefinition } = {}) {
    const body = { entry };
    if (input !== undefined) body.input = input;
    if (output !== undefined) body.output = output;
    if (schemaDefinition !== undefined) body.schema_definition = schemaDefinition;
    return this._request("POST", "/attestations/verify", body);
  }

  /** Do the stored runs still match what was signed? Also reports runs with no receipt. */
  reconcile(schemaId) {
    return this._request("GET", `/attestations/chains/${schemaId}/reconcile`);
  }

  // ── legacy: the older unsigned hash chain (prefer the receipts above) ──

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

module.exports = { IronThread, IronThreadError, verifyChain, canonical };
