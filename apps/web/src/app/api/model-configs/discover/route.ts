import { listModels } from "@/lib/connection-test";
import { db } from "@/lib/db";
import { decryptKey, err, httpUrl, isJson, LOCKED } from "@/lib/model-configs";
import { getSession } from "@/lib/session";

// POST /api/model-configs/discover { base_url, api_key?, id? } -> { models: string[] }
// Works before a config is saved (the model id is what you're trying to find). With no api_key but an id,
// the saved key of that config is used, but only for the URL it was saved with, so editing the URL to
// another server never sends that key there. Calls GET {base_url}/models, which costs nothing.
export async function POST(req: Request) {
  const s = await getSession();
  if (!s) return err("Sign in first.", 401);
  if (!isJson(req)) return err("Send application/json.", 415);
  const body = (await req.json().catch(() => null)) as { base_url?: unknown; api_key?: unknown; id?: unknown } | null;
  if (!body || !httpUrl(body.base_url)) return err("base_url is invalid.", 400);

  let key = typeof body.api_key === "string" && body.api_key.trim() ? body.api_key.trim() : null;
  if (!key && Number.isInteger(body.id)) {
    const row = db.prepare("SELECT * FROM model_configs WHERE id = ? AND user_id = ?").get(body.id as number, s.user.id);
    if (row?.api_key_enc && row.base_url === body.base_url) {
      if (!s.dek) return err(LOCKED, 423);
      key = decryptKey(row, s.user.id, s.dek);
    }
  }
  const r = await listModels(body.base_url as string, key);
  return r.ok ? Response.json({ models: r.models }) : err(r.message, 502);
}
