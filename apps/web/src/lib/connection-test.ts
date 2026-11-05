// Talks to any OpenAI-compatible server: OpenAI, OpenRouter, Ollama, LM Studio, llama.cpp, vLLM.
// No imports from the app, so `npm test` can load it directly.

const HTTP_HINTS: Record<number, string> = {
  401: "The API key was rejected",
  403: "The API key isn't allowed to use this model",
  404: "Not found: check the model id and base URL",
  429: "Rate limited or out of credit",
};

// Self-hosted servers load the model into memory on the first request, which can take a minute.
export const defaultTimeout = (provider: string) => (provider === "local" ? 120 : 30);

type Reply = { error?: { message?: string } | string; choices?: { message?: { content?: unknown } }[]; data?: { id?: unknown }[] };

// One request with plain-language failures. ponytail: verify_ssl isn't applied (Node's fetch has no
// per-request switch), so a self-signed HTTPS endpoint fails here.
async function call(url: string, apiKey: string | null, timeout: number, body?: object) {
  const started = Date.now();
  const done = <T extends object>(r: T) => ({ ...r, latency: Date.now() - started });
  try {
    const res = await fetch(url, {
      method: body ? "POST" : "GET",
      headers: { ...(body ? { "content-type": "application/json" } : {}), ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(timeout * 1000),
    });
    const text = await res.text();
    let json: Reply | undefined;
    try {
      json = JSON.parse(text);
    } catch {}
    if (!res.ok) {
      // Providers echo the key masked as a long "****" run; shorten it so the useful part of the message fits.
      const detail = ((typeof json?.error === "string" ? json.error : json?.error?.message) ?? text).replace(/\*{4,}/g, "…");
      return done({ ok: false as const, message: `${HTTP_HINTS[res.status] ?? `HTTP ${res.status}`}${detail ? `: ${detail.trim().slice(0, 200)}` : "."}` });
    }
    return done({ ok: true as const, json });
  } catch (e) {
    const err = e as { name?: string; cause?: { code?: string; message?: string } };
    if (err.name === "TimeoutError") return done({ ok: false as const, message: `No reply within ${timeout}s.` });
    const why = err.cause?.code ?? err.cause?.message; // e.g. ECONNREFUSED, ENOTFOUND, "bad port"
    return done({ ok: false as const, message: `Can't reach ${new URL(url).host}${why ? ` (${why})` : ""}.` });
  }
}

const endpoint = (baseUrl: string, path: string) => `${baseUrl.replace(/\/+$/, "")}/${path}`;

// One tiny chat completion: proves the URL is reachable, the key is accepted and the model answers.
// Sampling settings are left out on purpose; some models reject them and that isn't a connection problem.
export async function testConnection(
  cfg: { provider: string; base_url: string; model: string; request_timeout: number | null },
  apiKey: string | null,
) {
  const r = await call(endpoint(cfg.base_url, "chat/completions"), apiKey, cfg.request_timeout ?? defaultTimeout(cfg.provider), {
    model: cfg.model,
    messages: [{ role: "user", content: "Reply with the single word OK." }],
  });
  if (!r.ok) return { ok: false, message: r.message.slice(0, 300), latency: r.latency };
  const reply = r.json?.choices?.[0]?.message?.content;
  if (typeof reply !== "string") return { ok: false, message: "Connected, but the reply isn't an OpenAI-style chat completion. Check the base URL.", latency: r.latency };
  return { ok: true, message: `Replied "${reply.trim().slice(0, 60)}"`, latency: r.latency };
}

// GET /models: the model ids this server or key can use. Free on paid providers (no tokens).
export async function listModels(baseUrl: string, apiKey: string | null, timeout = 15) {
  const r = await call(endpoint(baseUrl, "models"), apiKey, timeout);
  if (!r.ok) return { ok: false as const, message: r.message.slice(0, 300) };
  const ids = (r.json?.data ?? []).map((m) => m.id).filter((id): id is string => typeof id === "string");
  if (!ids.length) return { ok: false as const, message: "The server answered but listed no models. Load or pull a model first." };
  return { ok: true as const, models: [...new Set(ids)].sort() };
}
