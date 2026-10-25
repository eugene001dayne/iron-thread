"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

const { verifyChain, canonical } = require("../verify");

const fixtures = path.join(__dirname, "fixtures");
const chain = JSON.parse(fs.readFileSync(path.join(fixtures, "chain.json"), "utf8"));
const cases = JSON.parse(fs.readFileSync(path.join(fixtures, "canonical_cases.json"), "utf8"));
const copy = (value) => JSON.parse(JSON.stringify(value));

// ── the proof that two languages agree ──────────────────────────────────────────────────────────────
// Every expected string below was produced by the PYTHON server code. JavaScript must reproduce it.

for (const c of cases.filter((x) => !x.known_difference)) {
  test(`canonical JSON matches Python: ${c.name}`, () => {
    assert.equal(canonical(JSON.parse(c.json)), c.expected);
  });
}

test("floats are the one known difference (and receipts contain none)", () => {
  const c = cases.find((x) => x.known_difference);
  assert.notEqual(canonical(JSON.parse(c.json)), c.expected);   // Python writes 1.0, JavaScript writes 1
  const numbers = [];
  const walk = (v) => {
    if (typeof v === "number") numbers.push(v);
    else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") Object.values(v).forEach(walk);
  };
  chain.entries.forEach((entry) => walk(entry.body));
  assert.ok(numbers.length > 0 && numbers.every(Number.isInteger), "a receipt body holds only whole numbers");
});

test("receipts signed by the Python server verify in JavaScript, including awkward unicode bodies", () => {
  const result = verifyChain(chain.entries, chain.public_key, { expectHead: chain.head, expectLength: 5 });
  assert.equal(result.ok, true, result.message);
  assert.match(result.message, /^OK: 5 entries/);
});

// ── every kind of damage is caught ──────────────────────────────────────────────────────────────────

test("an altered entry is rejected", () => {
  const damaged = copy(chain.entries);
  damaged[1].body.status = "passed";
  const result = verifyChain(damaged, chain.public_key);
  assert.equal(result.ok, false);
  assert.match(result.message, /entry 2: contents were altered/);
});

test("altering AND re-hashing an entry still fails, on the signature", () => {
  const crypto = require("node:crypto");
  const damaged = copy(chain.entries);
  damaged[4].body.status = "failed";
  damaged[4].entry_hash = crypto.createHash("sha256").update(canonical(damaged[4].body), "utf8").digest("hex");
  const result = verifyChain(damaged, chain.public_key);
  assert.equal(result.ok, false);
  assert.match(result.message, /entry 5: signature is not valid/);
});

test("the wrong public key is rejected", () => {
  const other = Buffer.alloc(32, 7).toString("base64");
  assert.match(verifyChain(chain.entries, other).message, /different key/);
});

test("deleted and reordered entries are rejected", () => {
  const deleted = copy(chain.entries);
  deleted.splice(1, 1);
  assert.equal(verifyChain(deleted, chain.public_key).ok, false);
  const swapped = copy(chain.entries);
  [swapped[0], swapped[1]] = [swapped[1], swapped[0]];
  assert.equal(verifyChain(swapped, chain.public_key).ok, false);
});

test("a truncated chain is invisible on its own, but caught by a pinned head or length", () => {
  const truncated = chain.entries.slice(0, 3);
  assert.equal(verifyChain(truncated, chain.public_key).ok, true);                                   // the known limit
  assert.match(verifyChain(truncated, chain.public_key, { expectHead: chain.head }).message, /truncated or rewritten/);
  assert.match(verifyChain(truncated, chain.public_key, { expectLength: 5 }).message, /expected 5/);
});

test("garbage input never throws, it just fails", () => {
  assert.equal(verifyChain([], chain.public_key).ok, false);
  assert.equal(verifyChain(undefined, chain.public_key).ok, false);
  assert.equal(verifyChain(chain.entries, "not-a-key").ok, false);
  assert.match(verifyChain([{}], chain.public_key).message, /malformed/);
  const noSignature = copy(chain.entries);
  delete noSignature[0].signature;
  assert.equal(verifyChain(noSignature, chain.public_key).ok, false);
  const badHash = copy(chain.entries);
  badHash[0].entry_hash = "xyz";
  assert.equal(verifyChain(badHash, chain.public_key).ok, false);
});
