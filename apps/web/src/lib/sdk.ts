// Server-side client for the local SDK server (PLAN 16.13). The browser never calls the SDK: the token stays here.
// `ab ui` starts both servers and hands this process AGENTBUILDER_API_URL and AGENTBUILDER_API_TOKEN.

export type SdkReply = { status: number; data: Record<string, unknown> };

const NOT_STARTED = "The SDK server is not running. Start the app with `ab ui`, which starts both.";

// Never throws: an unreachable SDK or a non-JSON answer becomes the same error shape the SDK uses.
export async function sdk(path: string, init?: { method?: string; body?: unknown }): Promise<SdkReply> {
  const base = process.env.AGENTBUILDER_API_URL;
  const token = process.env.AGENTBUILDER_API_TOKEN;
  if (!base || !token) return fail(503, NOT_STARTED);
  try {
    const res = await fetch(`${base}${path}`, {
      method: init?.method ?? "GET",
      headers: { "X-AgentBuilder-Token": token, ...(init?.body ? { "content-type": "application/json" } : {}) },
      body: init?.body ? JSON.stringify(init.body) : undefined,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(90_000), // the model check can wait for a slow provider
    });
    const data = await res.json().catch(() => null);
    return data && typeof data === "object" ? { status: res.status, data } : fail(502, `The SDK server answered HTTP ${res.status} without JSON.`);
  } catch {
    return fail(503, NOT_STARTED);
  }
}

const fail = (status: number, message: string): SdkReply => ({ status, data: { ok: false, errors: [{ field: "", message }] } });

export const relay = (r: SdkReply) => Response.json(r.data, { status: r.status });
