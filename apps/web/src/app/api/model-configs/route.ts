import { db } from "@/lib/db";
import { err, isJson, keyColumns, LOCKED, parseConfig, toPublic } from "@/lib/model-configs";
import { getSession } from "@/lib/session";

// GET /api/model-configs -> { configs, locked }
export async function GET() {
  const s = await getSession();
  if (!s) return err("Sign in first.", 401);
  const rows = db.prepare("SELECT * FROM model_configs WHERE user_id = ? ORDER BY name").all(s.user.id);
  return Response.json({ configs: rows.map(toPublic), locked: !s.dek });
}

// POST /api/model-configs { name, provider, base_url, model, api_key?, ...tuning } -> 201 config
export async function POST(req: Request) {
  const s = await getSession();
  if (!s) return err("Sign in first.", 401);
  if (!isJson(req)) return err("Send application/json.", 415);
  const parsed = parseConfig(await req.json().catch(() => null), false);
  if ("error" in parsed) return err(parsed.error!, 400);
  const key = keyColumns(parsed.apiKey, s.user.id, s.dek);
  if (!key) return err(LOCKED, 423);

  const cols: Record<string, string | number | null | Buffer> = { ...parsed.values, ...key, user_id: s.user.id };
  try {
    const { lastInsertRowid } = db
      .prepare(`INSERT INTO model_configs (${Object.keys(cols).join(", ")}) VALUES (${Object.keys(cols).map(() => "?").join(", ")})`)
      .run(...Object.values(cols));
    const row = db.prepare("SELECT * FROM model_configs WHERE id = ?").get(lastInsertRowid)!;
    return Response.json(toPublic(row), { status: 201 });
  } catch (e) {
    if (String(e).includes("UNIQUE")) return err("You already have a model config with that name.", 409);
    throw e;
  }
}
