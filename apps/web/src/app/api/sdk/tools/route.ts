import { relay, sdk } from "@/lib/sdk";
import { signedIn } from "@/lib/sdk-routes";

// GET /api/sdk/tools -> the SDK's tool basket: id, description, risk tier, side effects, network hosts.
export async function GET() {
  const a = await signedIn();
  if (a.error) return a.error;
  return relay(await sdk("/tools"));
}
