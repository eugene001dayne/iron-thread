"use strict";
/**
 * End to end: the JavaScript SDK against a REAL Iron-Thread server (not a mock).
 *
 *   python -m uvicorn main:app          # in the repo root
 *   node integration/e2e.js             # in sdk/iron-thread-js   (uses $IRONTHREAD_URL, default http://localhost:8000)
 *
 * It signs receipts with the Python server and verifies them here, in JavaScript.
 */
const assert = require("node:assert/strict");
const { IronThread, IronThreadError, verifyChain } = require("../index");

async function main() {
  const it = new IronThread();
  const schemaDefinition = {
    type: "object",
    required: ["customer", "amount"],
    properties: { customer: { type: "string" }, amount: { type: "number", minimum: 0 } },
  };

  const schema = await it.createSchema("js-sdk-e2e", schemaDefinition);
  const good = await it.validate({ customer: "Acme", amount: 120.5 }, schema.id);
  const bad = await it.validate('{"customer": "Acme", "amount": "about 120"}', schema.id);
  assert.equal(good.status, "passed");
  assert.equal(bad.status, "failed");
  assert.ok(good.attestation && bad.attestation, "every verdict gets a receipt");

  // Floats in the data are fine: only receipt BODIES are canonicalised here, and they hold no floats.
  const check = await it.verifyAttestation(good.attestation, { input: '{"customer":"Acme","amount":120.5}', schemaDefinition });
  assert.equal(check.valid, true);
  assert.equal(check.schema_matches, true);

  const [{ public_key: publicKey }] = await it.publicKeys();
  const chain = await it.getChain(schema.id);
  assert.equal(chain.length, 2);

  const offline = verifyChain(chain, publicKey, { expectHead: bad.attestation.entry_hash, expectLength: 2 });
  assert.equal(offline.ok, true, offline.message);
  assert.equal((await it.verifyChainOffline(schema.id, publicKey)).ok, true);
  assert.equal((await it.verifyChainRemote(schema.id)).valid, true);
  assert.equal((await it.reconcile(schema.id)).ok, true);

  const forged = JSON.parse(JSON.stringify(chain));
  forged[0].body.status = "failed";
  assert.equal(verifyChain(forged, publicKey).ok, false);
  assert.equal(verifyChain(chain.slice(0, 1), publicKey, { expectHead: bad.attestation.entry_hash }).ok, false);

  await assert.rejects(it.getAttestation("no-such-run"), (err) => err instanceof IronThreadError && err.status === 404);
  console.log("JavaScript SDK end-to-end against a real server: OK");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
