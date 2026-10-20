import { db } from "@/lib/db";
import { err, isJson, keyColumns, LOCKED, parseConfig, toPublic } from "@/lib/model-configs";
import { getSession } from "@/lib/session";

type Ctx = { params: Promise<{ id: string }> };

// Every query is scoped by user_id, so another user's id answers 404, not 403.
async function owned(ctx: Ctx) {
  const s = await getSession();
  const id = Number((await ctx.params).id);
  return { s, id: Number.isInteger(id) && id > 0 ? id : null };
}
const find = (id: number, userId: number) => db.prepare("SELECT * FROM model_configs WHERE id = ? AND user_id = ?").get(id, userId);

// GET /api/model-configs/:id
export async function GET(_req: Request, ctx: Ctx) {
  const { s, id } = await owned(ctx);
  if (!s) return err("Sign in first.", 401);
  const row = id && find(id, s.user.id);
  return row ? Response.json(toPublic(row)) : err("Not found.", 404);
}

// PATCH /api/model-configs/:id { any subset of fields; api_key: omit = keep, null or "" = remove }
export async function PATCH(req: Request, ctx: Ctx) {
  const { s, id } = await owned(ctx);
  if (!s) return err("Sign in first.", 401);
  if (!id) return err("Not found.", 404);
  if (!isJson(req)) return err("Send application/json.", 415);
  const parsed = parseConfig(await req.json().catch(() => null), true);
  if ("error" in parsed) return err(parsed.error!, 400);
  const key = keyColumns(parsed.apiKey, s.user.id, s.dek);
  if (!key) return err(LOCKED, 423);

  const before = find(id, s.user.id);
  if (!before) return err("Not found.", 404);
  const cols: Record<string, string | number | null | Buffer> = { ...parsed.values, ...key };
  // A different endpoint, model or key makes the last connection test meaningless.
  const changed = ["provider", "base_url", "model"].some((k) => k in parsed.values && parsed.values[k] !== before[k]);
  if (changed || parsed.apiKey !== undefined) Object.assign(cols, { tested_at: null, test_ok: null, test_message: null, test_latency_ms: null });
  const set = [...Object.keys(cols).map((k) => `${k} = ?`), "updated_at = datetime('now')"].join(", ");
  try {
    const { changes } = db.prepare(`UPDATE model_configs SET ${set} WHERE id = ? AND user_id = ?`).run(...Object.values(cols), id, s.user.id);
    if (!changes) return err("Not found.", 404);
  } catch (e) {
    if (String(e).includes("UNIQUE")) return err("You already have a model config with that name.", 409);
    throw e;
  }
  return Response.json(toPublic(find(id, s.user.id)!));
}

// DELETE /api/model-configs/:id -> 204
export async function DELETE(_req: Request, ctx: Ctx) {
  const { s, id } = await owned(ctx);
  if (!s) return err("Sign in first.", 401);
  const { changes } = id ? db.prepare("DELETE FROM model_configs WHERE id = ? AND user_id = ?").run(id, s.user.id) : { changes: 0 };
  return changes ? new Response(null, { status: 204 }) : err("Not found.", 404);
}
