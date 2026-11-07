import { err } from "@/lib/model-configs";
import { relay, sdk } from "@/lib/sdk";
import { jsonBody, signedIn, specWithSavedModel } from "@/lib/sdk-routes";

// POST /api/sdk/runs { spec, config_id, agent_mode, prompt, mock } -> 202 { run_id }. `mock` defaults to true:
// tools return canned answers and touch nothing live. A live run asks before every tier-2 call (see approvals route).
export async function POST(req: Request) {
  const a = await signedIn();
  if (a.error) return a.error;
  const b = await jsonBody(req);
  if (b.error) return b.error;
  if (typeof b.body.prompt !== "string") return err("prompt must be text.", 400);
  const s = specWithSavedModel(b.body, a.s.user.id);
  if (s.error) return s.error;
  return relay(await sdk("/runs", { method: "POST", body: { spec: s.spec, prompt: b.body.prompt, mock: b.body.mock !== false } }));
}
