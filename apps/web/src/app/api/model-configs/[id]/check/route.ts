import { modelFromConfig, type SavedModel } from "@/lib/agent-spec";
import { db } from "@/lib/db";
import { err, LOCKED } from "@/lib/model-configs";
import { relay, sdk } from "@/lib/sdk";
import { signedIn } from "@/lib/sdk-routes";

// POST /api/model-configs/:id/check -> { ok, tool_calling, agent_mode, message } from the SDK's model check
// (PLAN 4.4.1). One real request that requires a tool call; `agent_mode` is what the wizard writes into the spec.
export async function POST(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const a = await signedIn();
  if (a.error) return a.error;
  const id = Number((await ctx.params).id);
  const row = Number.isInteger(id)
    ? (db.prepare("SELECT * FROM model_configs WHERE id = ? AND user_id = ?").get(id, a.s.user.id) as SavedModel | undefined)
    : undefined;
  if (!row) return err("Not found.", 404);
  if (row.api_key_enc && !a.s.dek) return err(LOCKED, 423);
  const { agent_mode: _mode, ...model } = modelFromConfig(row);
  return relay(await sdk("/model/check", { method: "POST", body: { model } }));
}
