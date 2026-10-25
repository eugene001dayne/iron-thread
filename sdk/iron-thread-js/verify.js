"use strict";
/**
 * Offline verification of Iron-Thread receipts. Uses only Node's built-in crypto: no dependencies, no network.
 * A port of verify_offline.py; the tests check it against receipts signed by the Python server.
 */
const crypto = require("node:crypto");

const GENESIS = "0".repeat(64);
// DER prefix that wraps a raw 32-byte Ed25519 public key into a standard SPKI structure.
const SPKI_ED25519_PREFIX = Buffer.from("302a300506032b6570032100", "hex");
const HEX64 = /^[0-9a-f]{64}$/;

/** Order strings by Unicode code point, exactly as Python's sorted() does (not by UTF-16 unit). */
function compareCodePoints(a, b) {
  const x = Array.from(a);
  const y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    const d = x[i].codePointAt(0) - y[i].codePointAt(0);
    if (d !== 0) return d;
  }
  return x.length - y.length;
}

function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value !== null && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort(compareCodePoints)) out[key] = sortKeys(value[key]);
    return out;
  }
  return value;
}

/**
 * Deterministic JSON: sorted keys, no whitespace, UTF-8. Matches the server byte for byte for strings,
 * integers, booleans, null, arrays and objects. Floats are the one known difference: Python prints 1.0
 * and JavaScript prints 1. Receipt bodies contain no floats, so verification is unaffected.
 */
function canonical(value) {
  return JSON.stringify(sortKeys(value));
}

function sha256Hex(text) {
  return crypto.createHash("sha256").update(text, "utf8").digest("hex");
}

function fail(message) {
  return { ok: false, message };
}

/**
 * @param {object[]} entries  the list from IronThread#getChain(), oldest first
 * @param {string} publicKey  base64 Ed25519 public key you trust
 * @param {{expectHead?: string, expectLength?: number}} [options]
 * @returns {{ok: boolean, message: string}}
 */
function verifyChain(entries, publicKey, options = {}) {
  const { expectHead, expectLength } = options;
  if (!Array.isArray(entries) || entries.length === 0) return fail("the chain is empty");

  let raw;
  let keyObject;
  try {
    raw = Buffer.from(String(publicKey), "base64");
    if (raw.length !== 32) throw new Error("wrong length");
    keyObject = crypto.createPublicKey({ key: Buffer.concat([SPKI_ED25519_PREFIX, raw]), format: "der", type: "spki" });
  } catch {
    return fail("the public key is not a valid base64 Ed25519 key");
  }
  const keyId = crypto.createHash("sha256").update(raw).digest("hex").slice(0, 16);

  let prev = GENESIS;
  for (let i = 1; i <= entries.length; i++) {
    const entry = entries[i - 1];
    try {
      const body = entry.body;
      if (body.seq !== i) return fail(`entry ${i}: sequence number is ${body.seq} (gap, reorder, or missing start)`);
      if (body.prev_hash !== prev) return fail(`entry ${i}: broken link to the previous entry`);
      if (body.key_id !== keyId) return fail(`entry ${i}: signed by a different key than the one you supplied`);
      if (sha256Hex(canonical(body)) !== entry.entry_hash) return fail(`entry ${i}: contents were altered after signing`);
      if (!HEX64.test(entry.entry_hash)) throw new TypeError("entry_hash is not 64 hex characters");
      const good = crypto.verify(null, Buffer.from(entry.entry_hash, "hex"), keyObject, Buffer.from(entry.signature, "base64"));
      if (!good) return fail(`entry ${i}: signature is not valid for this key`);
    } catch (err) {
      return fail(`entry ${i}: malformed (${err.name}: ${err.message})`);
    }
    prev = entry.entry_hash;
  }

  if (expectLength !== undefined && entries.length !== expectLength) {
    return fail(`chain has ${entries.length} entries but you expected ${expectLength} (entries removed or added)`);
  }
  if (expectHead !== undefined && prev !== expectHead) {
    return fail("the newest entry's hash does not match the head you expected (truncated or rewritten)");
  }
  return { ok: true, message: `OK: ${entries.length} entries, all signed by key ${keyId}. Head hash: ${prev}` };
}

module.exports = { verifyChain, canonical, GENESIS };
