import { open, seal } from "./crypto";

// Model config fields the UI can tune, matching NAT's OpenAIModelConfig
// (.venv/.../nat/llm/openai_llm.py): model_name, base_url, api_key, temperature, top_p, seed,
// max_retries, request_timeout, verify_ssl. max_tokens passes through its extra="allow".
// "local" = any self-hosted OpenAI-compatible server (Ollama, LM Studio, llama.cpp, vLLM); they differ only in base URL.
export const PROVIDERS = ["openai", "openrouter", "local", "openai_compatible"] as const;

export type ModelConfig = {
  id: number;
  name: string;
  provider: (typeof PROVIDERS)[number];
  base_url: string;
  model: string;
  has_api_key: boolean;
  api_key_hint: string | null;
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  seed: number | null;
  request_timeout: number | null;
  max_retries: number;
  verify_ssl: boolean;
  tested_at: string | null;
  test_ok: boolean | null;
  test_message: string | null;
  test_latency_ms: number | null;
  updated_at: string;
};

const str = (min: number, max: number) => (v: unknown) => typeof v === "string" && v.trim().length >= min && v.length <= max;
const num = (min: number, max: number, int = false) => (v: unknown) =>
  typeof v === "number" && Number.isFinite(v) && v >= min && v <= max && (!int || Number.isInteger(v));
const nullable = (check: (v: unknown) => boolean) => (v: unknown) => v === null || check(v);
export const httpUrl = (v: unknown) => {
  if (typeof v !== "string" || v.length > 500) return false;
  try {
    return ["http:", "https:"].includes(new URL(v).protocol);
  } catch {
    return false;
  }
};

// Column name -> validator. Only these keys ever reach SQL, so column names are safe to interpolate.
const FIELDS: Record<string, (v: unknown) => boolean> = {
  name: str(1, 60),
  provider: (v) => PROVIDERS.includes(v as never),
  base_url: httpUrl,
  model: str(1, 200),
  temperature: nullable(num(0, 2)),
  top_p: nullable(num(0, 1)),
  max_tokens: nullable(num(1, 1_000_000, true)),
  seed: nullable(num(-(2 ** 31), 2 ** 31 - 1, true)),
  request_timeout: nullable(num(1, 600)),
  max_retries: num(0, 10, true),
  verify_ssl: (v) => typeof v === "boolean",
};
const REQUIRED = ["name", "provider", "base_url", "model"];

// `api_key`: undefined = keep the stored key, null or "" = remove it, string = replace it.
export function parseConfig(body: unknown, partial: boolean) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { error: "Body must be a JSON object." } as const;
  const input = body as Record<string, unknown>;
  const values: Record<string, string | number | null> = {};
  for (const [key, check] of Object.entries(FIELDS)) {
    if (!(key in input)) {
      if (!partial && REQUIRED.includes(key)) return { error: `${key} is required.` } as const;
      continue;
    }
    if (!check(input[key])) return { error: `${key} is invalid.` } as const;
    const v = input[key];
    values[key] = typeof v === "boolean" ? Number(v) : typeof v === "string" ? v.trim() : (v as number | null);
  }
  const k = input.api_key;
  if (k !== undefined && k !== null && !(typeof k === "string" && k.length <= 1000)) return { error: "api_key is invalid." } as const;
  const apiKey = typeof k === "string" && k.trim() ? k.trim() : k === undefined ? undefined : null;
  return { values, apiKey } as const;
}

// Never returns the key or its ciphertext.
export function toPublic(row: Record<string, unknown>): ModelConfig {
  const { api_key_enc, user_id: _u, created_at: _c, verify_ssl, test_ok, ...rest } = row;
  return {
    ...(rest as Omit<ModelConfig, "has_api_key" | "verify_ssl" | "test_ok">),
    has_api_key: api_key_enc != null,
    verify_ssl: verify_ssl === 1,
    test_ok: test_ok == null ? null : test_ok === 1,
  };
}

export const keyAad = (userId: number) => `api_key:${userId}`;

// Column values for an api_key change, or null when the data key is locked and a new key can't be sealed.
export function keyColumns(apiKey: string | null | undefined, userId: number, dek: Buffer | undefined): Record<string, Buffer | string | null> | null {
  if (apiKey === undefined) return {};
  if (apiKey === null) return { api_key_enc: null, api_key_hint: null };
  if (!dek) return null;
  return { api_key_enc: seal(dek, Buffer.from(apiKey), keyAad(userId)), api_key_hint: apiKey.slice(-4) };
}

// HTTP helpers for the /api/model-configs route handlers.
export const err = (error: string, status: number) => Response.json({ error }, { status });
// JSON-only bodies: a cross-site form can't send this content type without a CORS preflight.
export const isJson = (req: Request) => req.headers.get("content-type")?.startsWith("application/json") ?? false;
export const LOCKED = "Your encryption key is locked. Unlock it in Settings, then try again.";

// The plain API key, for calling the provider. Only ever held in memory for the request.
export function decryptKey(row: Record<string, unknown>, userId: number, dek: Buffer): string | null {
  return row.api_key_enc ? open(dek, row.api_key_enc as Uint8Array, keyAad(userId)).toString() : null;
}
