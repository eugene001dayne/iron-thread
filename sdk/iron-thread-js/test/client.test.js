"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

const { IronThread, IronThreadError } = require("../index");

const chain = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", "chain.json"), "utf8"));

/** A fake fetch: records every call and answers from a table of canned replies. */
function fakeFetch(replies) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, ...init, body: init.body ? JSON.parse(init.body) : undefined });
    const reply = replies[`${init.method} ${new URL(url).pathname}`];
    if (!reply) return { ok: false, status: 404, text: async () => JSON.stringify({ detail: "no such route" }) };
    const status = reply.status || 200;
    const body = typeof reply.body === "string" ? reply.body : JSON.stringify(reply.body);
    return { ok: status < 400, status, text: async () => body };
  };
  fn.calls = calls;
  return fn;
}

function withEnv(vars, fn) {
  const saved = {};
  for (const k of Object.keys(vars)) {
    saved[k] = process.env[k];
    if (vars[k] === undefined) delete process.env[k];
    else process.env[k] = vars[k];
  }
  try {
    return fn();
  } finally {
    for (const k of Object.keys(saved)) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }
}

test("defaults to localhost, then the environment, then explicit arguments", () => {
  withEnv({ IRONTHREAD_URL: undefined, IRONTHREAD_API_KEY: undefined }, () => {
    assert.equal(new IronThread().baseUrl, "http://localhost:8000");
    assert.equal(new IronThread().apiKey, null);
  });
  withEnv({ IRONTHREAD_URL: "http://env.test:9000/", IRONTHREAD_API_KEY: "env-key" }, () => {
    const fromEnv = new IronThread();
    assert.equal(fromEnv.baseUrl, "http://env.test:9000");
    assert.equal(fromEnv.apiKey, "env-key");
    const explicit = new IronThread("http://x.test", { apiKey: "arg-key" });
    assert.equal(explicit.baseUrl, "http://x.test");
    assert.equal(explicit.apiKey, "arg-key");
    const object = new IronThread({ baseUrl: "http://y.test/", apiKey: "obj-key" });
    assert.equal(object.baseUrl, "http://y.test");
    assert.equal(object.apiKey, "obj-key");
  });
});

test("sends the API key as a Bearer header only when there is one", async () => {
  const f = fakeFetch({ "GET /health": { body: { status: "ok" } } });
  await new IronThread("http://t", { fetch: f, apiKey: "secret-key" }).health();
  assert.equal(f.calls[0].headers.Authorization, "Bearer secret-key");
  await withEnv({ IRONTHREAD_API_KEY: undefined }, () => new IronThread("http://t", { fetch: f }).health());
  assert.equal(f.calls[1].headers.Authorization, undefined);
});

test("validate serialises objects, and returns the receipt", async () => {
  const f = fakeFetch({ "POST /validate": { body: { run_id: "r1", status: "passed", attestation: { entry_hash: "h" } } } });
  const it = new IronThread("http://t", { fetch: f });
  const result = await it.validate({ amount: 5 }, "schema-1", "gpt", true);
  assert.deepEqual(f.calls[0].body, {
    ai_output: '{"amount":5}', schema_id: "schema-1", model_used: "gpt", auto_correct: true,
  });
  assert.equal(result.attestation.entry_hash, "h");
  await it.validate('{"a":1}', "schema-1");
  assert.equal(f.calls[1].body.ai_output, '{"a":1}');
});

test("validateBatch serialises each object", async () => {
  const f = fakeFetch({ "POST /validate/batch": { body: { total: 2 } } });
  await new IronThread("http://t", { fetch: f }).validateBatch([{ a: 1 }, "x"], "s");
  assert.deepEqual(f.calls[0].body.ai_outputs, ['{"a":1}', "x"]);
});

test("server errors carry the server's explanation", async () => {
  const f = fakeFetch({ "GET /schemas": { status: 401, body: { detail: "Missing or invalid API key." } } });
  await assert.rejects(new IronThread("http://t", { fetch: f }).listSchemas(), (err) => {
    assert.ok(err instanceof IronThreadError && err instanceof Error);
    assert.equal(err.status, 401);
    assert.equal(err.detail, "Missing or invalid API key.");
    assert.match(err.message, /401.*Missing or invalid API key/);
    return true;
  });
});

test("non-JSON error bodies are still reported", async () => {
  const f = fakeFetch({ "GET /schemas": { status: 502, body: "<html>bad gateway</html>" } });
  await assert.rejects(new IronThread("http://t", { fetch: f }).listSchemas(), (err) => err.detail.includes("bad gateway"));
});

test("an unreachable server gives a friendly message with status 0", async () => {
  const refuse = async () => { throw new TypeError("fetch failed"); };
  await assert.rejects(new IronThread("http://t", { fetch: refuse }).health(), (err) => {
    assert.equal(err.status, 0);
    assert.match(err.message, /Cannot reach Iron-Thread|cannot reach Iron-Thread/);
    assert.match(err.message, /python -m uvicorn main:app/);
    assert.ok(err.cause instanceof TypeError);
    return true;
  });
});

test("verifyAttestation only sends what you supply", async () => {
  const f = fakeFetch({ "POST /attestations/verify": { body: { valid: true } } });
  const it = new IronThread("http://t", { fetch: f });
  await it.verifyAttestation({ body: {} });
  assert.deepEqual(Object.keys(f.calls[0].body), ["entry"]);
  await it.verifyAttestation({ body: {} }, { input: "i", output: { a: 1 }, schemaDefinition: { type: "object" } });
  assert.deepEqual(Object.keys(f.calls[1].body).sort(), ["entry", "input", "output", "schema_definition"]);
});

test("verifyChainOffline fetches a chain and checks it locally", async () => {
  const f = fakeFetch({ "GET /attestations/chains/abc": { body: { chain_id: "abc", entries: chain.entries } } });
  const it = new IronThread("http://t", { fetch: f });
  const ok = await it.verifyChainOffline("abc", chain.public_key, { expectHead: chain.head });
  assert.equal(ok.ok, true, ok.message);
  const wrongHead = await it.verifyChainOffline("abc", chain.public_key, { expectHead: "0".repeat(64) });
  assert.equal(wrongHead.ok, false);
});

test("publicKeys, getChain, reconcile and exportRuns read the right endpoints", async () => {
  const f = fakeFetch({
    "GET /attestations/keys": { body: { keys: [{ key_id: "k", public_key: "p" }] } },
    "GET /attestations/chains/s": { body: { entries: [1, 2] } },
    "GET /attestations/chains/s/reconcile": { body: { ok: true } },
    "GET /runs/export": { body: "id,status\n1,passed\n" },
  });
  const it = new IronThread("http://t", { fetch: f });
  assert.deepEqual(await it.publicKeys(), [{ key_id: "k", public_key: "p" }]);
  assert.deepEqual(await it.getChain("s"), [1, 2]);
  assert.deepEqual(await it.reconcile("s"), { ok: true });
  assert.equal(await it.exportRuns(), "id,status\n1,passed\n");
});
