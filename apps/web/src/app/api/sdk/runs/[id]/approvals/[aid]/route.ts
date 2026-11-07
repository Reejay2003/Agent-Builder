import { err } from "@/lib/model-configs";
import { relay, sdk } from "@/lib/sdk";
import { jsonBody, signedIn } from "@/lib/sdk-routes";

// POST /api/sdk/runs/:id/approvals/:aid { approved } -> the person's answer to one tier-2 call.
export async function POST(req: Request, ctx: { params: Promise<{ id: string; aid: string }> }) {
  const a = await signedIn();
  if (a.error) return a.error;
  const b = await jsonBody(req);
  if (b.error) return b.error;
  const { id, aid } = await ctx.params;
  if (!/^[0-9a-f]{32}$/.test(id) || !/^[0-9a-f]{16}$/.test(aid)) return err("Unknown approval.", 404);
  if (typeof b.body.approved !== "boolean") return err("approved must be true or false.", 400);
  return relay(await sdk(`/runs/${id}/approvals/${aid}`, { method: "POST", body: { approved: b.body.approved } }));
}
