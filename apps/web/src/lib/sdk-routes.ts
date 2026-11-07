import { modelFromConfig, type AgentMode, type SavedModel } from "./agent-spec";
import { db } from "./db";
import { err, isJson } from "./model-configs";
import { getSession } from "./session";

const MODES = ["auto", "tool_calling", "react"];

// Shared checks for the browser-facing /api/sdk routes: signed in, JSON body (a cross-site form can't send it
// without a CORS preflight), and a spec whose model section is rebuilt from the user's saved config.
export async function signedIn() {
  const s = await getSession();
  return s ? { s } : { error: err("Sign in first.", 401) };
}

export async function jsonBody(req: Request) {
  if (!isJson(req)) return { error: err("Send application/json.", 415) };
  const body = (await req.json().catch(() => null)) as Record<string, unknown> | null;
  return body && typeof body === "object" && !Array.isArray(body) ? { body } : { error: err("Body must be a JSON object.", 400) };
}

export function specWithSavedModel(body: Record<string, unknown>, userId: number) {
  const spec = body.spec;
  if (!spec || typeof spec !== "object" || Array.isArray(spec)) return { error: err("spec must be an object.", 400) };
  const row = Number.isInteger(body.config_id)
    ? (db.prepare("SELECT * FROM model_configs WHERE id = ? AND user_id = ?").get(body.config_id as number, userId) as SavedModel | undefined)
    : undefined;
  if (!row) return { error: err("Save a model config first (step 1).", 400) };
  const mode = MODES.includes(body.agent_mode as string) ? (body.agent_mode as AgentMode) : "auto";
  return { spec: { ...(spec as object), model: modelFromConfig(row, mode) } };
}
