const BASE_URL = 'https://iron-thread-production.up.railway.app';

class IronThread {
  constructor(host = BASE_URL) {
    this.host = host.replace(/\/$/, '');
  }

  async createSchema(name, schemaDefinition, description = '') {
    const res = await fetch(`${this.host}/schemas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        description,
        schema_definition: schemaDefinition
      })
    });
    const data = await res.json();
    return data[0];
  }

  async listSchemas() {
    const res = await fetch(`${this.host}/schemas`);
    return res.json();
  }

  async validate(aiOutput, schemaId, modelUsed = 'unknown') {
    if (typeof aiOutput !== 'string') {
      aiOutput = JSON.stringify(aiOutput);
    }
    const res = await fetch(`${this.host}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        schema_id: schemaId,
        ai_output: aiOutput,
        model_used: modelUsed
      })
    });
    const data = await res.json();
    return {
      passed: data.status === 'passed',
      status: data.status,
      reason: data.reason,
      data: data.validated_output,
      latencyMs: data.latency_ms,
      runId: data.run_id
    };
  }

  async validateBatch(aiOutputs, schemaId, modelUsed = 'unknown') {
    const outputs = aiOutputs.map(o => typeof o === 'string' ? o : JSON.stringify(o));
    const res = await fetch(`${this.host}/validate/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        schema_id: schemaId,
        ai_outputs: outputs,
        model_used: modelUsed
      })
    });
    const data = await res.json();
    return {
      total: data.total,
      passed: data.passed,
      failed: data.failed,
      successRate: data.success_rate,
      results: data.results.map(r => ({
        passed: r.status === 'passed',
        status: r.status,
        reason: r.reason,
        data: r.validated_output,
        latencyMs: r.latency_ms,
        runId: r.run_id
      }))
    };
  }

  async createWebhook(name, url, onFailure = true, onSuccess = false, schemaId = null) {
    const res = await fetch(`${this.host}/webhooks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        url,
        on_failure: onFailure,
        on_success: onSuccess,
        schema_id: schemaId
      })
    });
    const data = await res.json();
    return data[0];
  }

  async listWebhooks() {
    const res = await fetch(`${this.host}/webhooks`);
    return res.json();
  }

  async deleteWebhook(webhookId) {
    const res = await fetch(`${this.host}/webhooks/${webhookId}`, {
      method: 'DELETE'
    });
    return res.json();
  }

  async stats() {
    const res = await fetch(`${this.host}/dashboard/stats`);
    return res.json();
  }

  async runs() {
    const res = await fetch(`${this.host}/runs`);
    return res.json();
  }

  async health() {
    const res = await fetch(`${this.host}/health`);
    return res.json();
  }

  async analyticsTrends() {
    const res = await fetch(`${this.host}/analytics/trends`);
    return res.json();
  }

  async analyticsModels() {
    const res = await fetch(`${this.host}/analytics/models`);
    return res.json();
  }

  async analyticsSchemas() {
    const res = await fetch(`${this.host}/analytics/schemas`);
    return res.json();
  }

  async analyticsErrors() {
    const res = await fetch(`${this.host}/analytics/errors`);
    return res.json();
  }
}

// Convenience functions
const _defaultClient = new IronThread();

async function validate(aiOutput, schemaId, modelUsed = 'unknown') {
  return _defaultClient.validate(aiOutput, schemaId, modelUsed);
}

async function validateBatch(aiOutputs, schemaId, modelUsed = 'unknown') {
  return _defaultClient.validateBatch(aiOutputs, schemaId, modelUsed);
}

module.exports = { IronThread, validate, validateBatch };