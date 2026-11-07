import { relay, sdk } from "@/lib/sdk";
import { jsonBody, signedIn, specWithSavedModel } from "@/lib/sdk-routes";

// POST /api/sdk/validate { spec, config_id, agent_mode } -> the SDK's verdict and the YAML it writes.
export async function POST(req: Request) {
  const a = await signedIn();
  if (a.error) return a.error;
  const b = await jsonBody(req);
  if (b.error) return b.error;
  const s = specWithSavedModel(b.body, a.s.user.id);
  if (s.error) return s.error;
  return relay(await sdk("/spec/validate", { method: "POST", body: { spec: s.spec } }));
}
