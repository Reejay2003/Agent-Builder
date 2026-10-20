import { db } from "@/lib/db";
import { testConnection } from "@/lib/connection-test";
import { decryptKey, err, LOCKED, toPublic } from "@/lib/model-configs";
import { getSession } from "@/lib/session";

// POST /api/model-configs/:id/test -> config with tested_at, test_ok, test_message, test_latency_ms
// Makes one real request to the provider, so it can cost a fraction of a cent.
export async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const s = await getSession();
  if (!s) return err("Sign in first.", 401);
  const id = Number((await ctx.params).id);
  const find = () => db.prepare("SELECT * FROM model_configs WHERE id = ? AND user_id = ?").get(id, s.user.id);
  const row = Number.isInteger(id) ? find() : undefined;
  if (!row) return err("Not found.", 404);
  if (row.api_key_enc && !s.dek) return err(LOCKED, 423);

  const r = await testConnection(row as { provider: string; base_url: string; model: string; request_timeout: number | null }, decryptKey(row, s.user.id, s.dek!));
  db.prepare("UPDATE model_configs SET tested_at = datetime('now'), test_ok = ?, test_message = ?, test_latency_ms = ? WHERE id = ? AND user_id = ?")
    .run(Number(r.ok), r.message, r.latency, id, s.user.id);
  return Response.json(toPublic(find()!));
}
