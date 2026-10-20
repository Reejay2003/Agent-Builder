// Run: npm test. A fake OpenAI-compatible server on a random local port; no real provider is called.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { after, before, test } from "node:test";
import { defaultTimeout, listModels, testConnection } from "./connection-test.ts";

let base;
const server = createServer((req, res) => {
  let body = "";
  req.on("data", (c) => (body += c));
  req.on("end", () => {
    const { model } = JSON.parse(body || "{}");
    const send = (status, json) => res.writeHead(status, { "content-type": "application/json" }).end(JSON.stringify(json));
    // Like a self-hosted server: no key needed to list models; duplicates and junk entries get cleaned up.
    if (req.method === "GET" && req.url === "/v1/models") return send(200, { data: [{ id: "qwen2.5:7b" }, { id: "llama3.2:latest" }, { id: "qwen2.5:7b" }, { id: 42 }] });
    if (req.method === "GET" && req.url === "/empty/models") return send(200, { data: [] });
    if (req.url !== "/v1/chat/completions") return send(404, { error: { message: "no such route" } });
    if (req.headers.authorization !== "Bearer sk-good")
      return send(401, { error: { message: `Incorrect API key provided: sk-proj-${"*".repeat(150)}abcd. You can find your API key at https://platform.openai.com/account/api-keys.` } });
    if (model === "missing") return send(404, { error: { message: "The model `missing` does not exist" } });
    if (model === "slow") return setTimeout(() => send(200, {}), 3000);
    if (model === "weird") return send(200, { result: "not a chat completion" });
    send(200, { choices: [{ message: { role: "assistant", content: " OK " } }] });
  });
});
before(() => new Promise((r) => server.listen(0, "127.0.0.1", () => ((base = `http://127.0.0.1:${server.address().port}/v1`), r()))));
after(() => server.close());

const cfg = (model, extra = {}) => ({ provider: "openai", base_url: base, model, request_timeout: null, ...extra });

test("success reports the reply and latency", async () => {
  const r = await testConnection(cfg("gpt-test"), "sk-good");
  assert.equal(r.ok, true);
  assert.equal(r.message, 'Replied "OK"');
  assert.ok(r.latency >= 0);
});

test("trailing slash on the base URL is fine", async () => {
  assert.equal((await testConnection(cfg("gpt-test", { base_url: `${base}/` }), "sk-good")).ok, true);
});

test("wrong key, unknown model and a non-chat reply explain themselves", async () => {
  assert.equal(
    (await testConnection(cfg("gpt-test"), "sk-bad")).message,
    "The API key was rejected: Incorrect API key provided: sk-proj-…abcd. You can find your API key at https://platform.openai.com/account/api-keys.",
  );
  assert.match((await testConnection(cfg("gpt-test"), null)).message, /^The API key was rejected/);
  assert.match((await testConnection(cfg("missing"), "sk-good")).message, /^Not found: check the model id and base URL: The model `missing`/);
  assert.match((await testConnection(cfg("weird"), "sk-good")).message, /isn't an OpenAI-style chat completion/);
});

test("timeout and unreachable host fail cleanly", async () => {
  assert.equal((await testConnection(cfg("slow", { request_timeout: 1 }), "sk-good")).message, "No reply within 1s.");
  // A port that was just freed, so nothing is listening on it.
  const closed = createServer();
  await new Promise((r) => closed.listen(0, "127.0.0.1", r));
  const { port } = closed.address();
  await new Promise((r) => closed.close(r));
  const r = await testConnection(cfg("x", { base_url: `http://127.0.0.1:${port}/v1` }), "sk-good");
  assert.equal(r.ok, false);
  assert.equal(r.message, `Can't reach 127.0.0.1:${port} (ECONNREFUSED).`);
});

test("listModels returns sorted unique ids and explains an empty server", async () => {
  assert.deepEqual(await listModels(base, null), { ok: true, models: ["llama3.2:latest", "qwen2.5:7b"] });
  assert.match((await listModels(base.replace("/v1", "/empty"), null)).message, /listed no models/);
});

test("self-hosted servers get a longer default timeout for the first model load", () => {
  assert.equal(defaultTimeout("local"), 120);
  assert.equal(defaultTimeout("openai"), 30);
});
