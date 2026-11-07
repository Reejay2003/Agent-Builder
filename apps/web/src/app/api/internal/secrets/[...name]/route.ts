import { configIdOf, isLoopbackHost, sameToken } from "@/lib/vault";
import { db } from "@/lib/db";
import { decryptKey } from "@/lib/model-configs";
import { unlockedKeyFor } from "@/lib/session";

// GET /api/internal/secrets/modelcfg/<id>/api_key -> { value } (PLAN 16.13). Called only by the local SDK server when
// a run or the model check starts; it sends AGENTBUILDER_VAULT_TOKEN in X-AgentBuilder-Token.
// 200 the key; 401 wrong token; 403 not loopback or a browser; 404 unknown name; 423 the vault is locked.
// The value is never logged and never cached.
const answer = (status: number, body: object) =>
  Response.json(body, { status, headers: { "cache-control": "no-store" } });

export async function GET(req: Request, ctx: { params: Promise<{ name: string[] }> }) {
  if (!isLoopbackHost(req.headers.get("host")) || req.headers.get("origin")) return answer(403, { error: "Not allowed." });
  if (!sameToken(req.headers.get("x-agentbuilder-token"), process.env.AGENTBUILDER_VAULT_TOKEN)) return answer(401, { error: "Wrong token." });
  const id = configIdOf((await ctx.params).name.join("/"));
  const row = id ? (db.prepare("SELECT * FROM model_configs WHERE id = ?").get(id) as Record<string, unknown> | undefined) : undefined;
  if (!row?.api_key_enc) return answer(404, { error: "Unknown secret." });
  const userId = row.user_id as number;
  const dek = unlockedKeyFor(userId);
  if (!dek) return answer(423, { error: "The vault is locked. Sign in to the web app and unlock it, then retry." });
  return answer(200, { value: decryptKey(row, userId, dek) });
}
