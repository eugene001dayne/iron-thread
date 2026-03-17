const BASE_URL = 'https://iron-thread-production.up.railway.app';

class IronThread {
  constructor(host = BASE_URL) {
    this.host = host.replace(/\/$/, '');
  }

  async _request(method, path, body = null) {
    const options = {
      method,
      headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);
    const res = await fetch(`${this.host}${path}`);
    if (!res.ok) throw new Error(`Iron-Thread API error: ${res.status}`);
    return res.json();
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

  async stats() {
    const res = await fetch(`${this.host}/dashboard/stats`);
    return res.json();
  }

  async runs() {
    const res = await fetch(`${this.host}/runs`);
    return res.json();
  }
}

// Convenience function for quick use
const _defaultClient = new IronThread();

async function validate(aiOutput, schemaId, modelUsed = 'unknown') {
  return _defaultClient.validate(aiOutput, schemaId, modelUsed);
}

module.exports = { IronThread, validate };