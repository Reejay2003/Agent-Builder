// Run: npm test (node strips the types from the .ts files itself).
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildSpec, modelFromConfig, slug } from "./agent-spec.ts";
import { configIdOf, isLoopbackHost, sameToken } from "./vault.ts";

const row = { id: 7, provider: "local", base_url: "http://localhost:11434/v1", model: "qwen3", temperature: 0, max_tokens: null, api_key_enc: null };

test("the model section comes from the saved config and names the key only by reference", () => {
  assert.deepEqual(modelFromConfig(row, "react"), { provider: "openai_compatible", model: "qwen3", base_url: "http://localhost:11434/v1", temperature: 0, agent_mode: "react" });
  const withKey = modelFromConfig({ ...row, provider: "openai", api_key_enc: Buffer.from("x") });
  assert.equal(withKey.credential_ref, "secret://modelcfg/7/api_key");
  assert.equal(withKey.provider, "openai");
  assert.equal(withKey.agent_mode, "auto");
});

test("the spec is JSON the SDK schema accepts: rules split, tools as ids, tier 2 asks a human", () => {
  const spec = buildSpec({ name: "a", type: "personal", model: null, persona: "p", rules: "one\n\n  two  \n", tools: ["gmail.read"], guardrails: "strict" });
  assert.deepEqual(spec.instructions, { persona: "p", rules: ["one", "two"] });
  assert.deepEqual(spec.tools, [{ id: "gmail.read" }]);
  assert.equal(spec.approvals.tier2_external_comms, "require_human");
  assert.equal("config_id" in spec.model || "verify_ssl" in spec.model, false);
});

test("the vault serves only modelcfg/<id>/api_key names", () => {
  assert.equal(configIdOf("modelcfg/3/api_key"), 3);
  for (const bad of ["modelcfg/0/api_key", "modelcfg/3/other", "modelcfg/3/api_key/x", "../modelcfg/3/api_key", "modelcfg/-1/api_key", "x"]) {
    assert.equal(configIdOf(bad), null, bad);
  }
});

test("the vault token check needs an exact match and the host must be loopback", () => {
  assert.ok(sameToken("abc", "abc"));
  for (const [given, expected] of [["abc", "abd"], ["ab", "abc"], [null, "abc"], ["abc", undefined], ["", ""]]) {
    assert.equal(sameToken(given, expected), false);
  }
  assert.ok(isLoopbackHost("127.0.0.1:3000") && isLoopbackHost("localhost") && isLoopbackHost("[::1]:3000"));
  assert.ok(!isLoopbackHost("evil.example:3000") && !isLoopbackHost(null) && !isLoopbackHost("127.0.0.1.evil.example"));
});

test("the spec name is a slug the SDK accepts; the typed name stays for display", () => {
  assert.equal(slug("Inbox helper"), "inbox-helper");
  assert.equal(slug("  Ünïcode — Agent!! "), "unicode-agent");
  assert.equal(slug("---"), "agent");
  assert.equal(slug("x".repeat(80)).length, 63);
  assert.match(slug("_Weird__Name_"), /^[a-z0-9][a-z0-9_-]*$/);
  const spec = buildSpec({ name: "Inbox helper", type: "personal", model: null, persona: "", rules: "", tools: [], guardrails: "standard" });
  assert.equal(spec.name, "inbox-helper");
  assert.equal(spec.metadata.display_name, "Inbox helper");
});
