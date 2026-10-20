// Run: npm test (node strips the types from crypto.ts itself).
import assert from "node:assert/strict";
import { test } from "node:test";
import { deriveKey, hashPassword, normalizePhrase, open, randomKey, randomSalt, recoveryPhrase, seal, verifyPassword } from "./crypto.ts";

test("password hash verifies only the right password", () => {
  const stored = hashPassword("correct horse");
  assert.ok(verifyPassword("correct horse", stored));
  assert.ok(!verifyPassword("wrong horse", stored));
});

test("envelope: data key wrapped by a derived key, API key sealed by the data key", () => {
  const salt = randomSalt();
  const dek = randomKey();
  const wrapped = seal(deriveKey("pw-123456", salt), dek, "dek");
  const unwrapped = open(deriveKey("pw-123456", salt), wrapped, "dek");
  assert.deepEqual(unwrapped, dek);

  const blob = seal(unwrapped, Buffer.from("sk-secret"), "api_key:1");
  assert.ok(!blob.includes(Buffer.from("sk-secret")));
  assert.equal(open(dek, blob, "api_key:1").toString(), "sk-secret");

  assert.throws(() => open(deriveKey("other-password", salt), wrapped, "dek"));
  assert.throws(() => open(dek, blob, "api_key:2"), "blob must not open for another user");
});

test("recovery phrase: 6 groups of 4, unique, typed back in any form", () => {
  const p = recoveryPhrase();
  assert.match(p, /^([A-HJKMNP-TV-Z0-9]{4}-){5}[A-HJKMNP-TV-Z0-9]{4}$/);
  assert.notEqual(p, recoveryPhrase());
  assert.equal(normalizePhrase(` ${p.toLowerCase().replaceAll("-", " ")} `), p.replaceAll("-", ""));
});
