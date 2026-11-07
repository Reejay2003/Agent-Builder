import { err } from "@/lib/model-configs";
import { relay, sdk } from "@/lib/sdk";
import { signedIn } from "@/lib/sdk-routes";

// GET /api/sdk/runs/:id -> status, pending approvals with their exact arguments, answer, warnings and trace.
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const a = await signedIn();
  if (a.error) return a.error;
  const { id } = await ctx.params;
  if (!/^[0-9a-f]{32}$/.test(id)) return err("Unknown run.", 404);
  return relay(await sdk(`/runs/${id}`));
}
