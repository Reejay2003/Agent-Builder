// The AgentSpec the wizard sends to the SDK (PLAN 16.13), built as plain JSON: the SDK validates it and writes the
// YAML, the UI never does. Used in the browser (the wizard) and on the server; no imports, so `npm test` loads it.

export type SavedModel = { id: number; provider: string; base_url: string; model: string; temperature: number | null; max_tokens: number | null; api_key_enc?: unknown };
export type AgentMode = "auto" | "tool_calling" | "react";

// The web app's providers -> the SDK's. Self-hosted servers all speak the OpenAI API at their own base URL.
const PROVIDER: Record<string, string> = { openai: "openai", openrouter: "openrouter", local: "openai_compatible", openai_compatible: "openai_compatible" };

// The model section ALWAYS comes from the saved config, never from the browser: the key may only ever be sent to the
// URL it was saved with (`secret://modelcfg/<id>/api_key` is resolved by the SDK through the vault endpoint).
export function modelFromConfig(row: SavedModel, agentMode: AgentMode = "auto") {
  return {
    provider: PROVIDER[row.provider] ?? "openai_compatible",
    model: row.model,
    base_url: row.base_url,
    ...(row.api_key_enc ? { credential_ref: `secret://modelcfg/${row.id}/api_key` } : {}),
    ...(row.temperature !== null ? { temperature: row.temperature } : {}),
    ...(row.max_tokens !== null ? { max_tokens: row.max_tokens } : {}),
    agent_mode: agentMode,
  };
}

export type SpecInput = {
  name: string;
  type: string;
  model: ReturnType<typeof modelFromConfig> | null;
  persona: string;
  rules: string;
  tools: string[];
  guardrails: string;
};

// The SDK's spec name is a slug (lowercase letters, digits, "-" or "_", at most 63, starting with a letter or digit);
// the name as typed is kept in metadata for display.
export const slug = (name: string) =>
  name.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^[-_]+|-+$/g, "").slice(0, 63) || "agent";

export function buildSpec(i: SpecInput) {
  return {
    spec_version: 1,
    name: slug(i.name),
    metadata: { display_name: i.name },
    type: i.type,
    model: i.model ?? { provider: "openai", model: "pick-a-model", agent_mode: "auto" },
    instructions: { persona: i.persona, rules: i.rules.split("\n").map((r) => r.trim()).filter(Boolean) },
    tools: i.tools.map((id) => ({ id })),
    guardrails: { profile: i.guardrails },
    approvals: { tier2_external_comms: "require_human" },
  };
}
