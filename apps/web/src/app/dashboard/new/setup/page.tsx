import { redirect } from "next/navigation";
import { db } from "@/lib/db";
import { toPublic } from "@/lib/model-configs";
import { getSession } from "@/lib/session";
import { templates } from "../templates";
import { Wizard } from "./wizard";

// Session read in the layout blocks; opt the page out too or sibling navigation is flagged.
export const instant = false;

export default async function Setup({ searchParams }: { searchParams: Promise<{ [k: string]: string | string[] | undefined }> }) {
  const { name, template } = await searchParams;
  const t = templates.find((x) => x.id === template && x.ready);
  if (typeof name !== "string" || !name.trim() || !t?.toolset) redirect("/dashboard/new");
  const s = await getSession();
  if (!s) redirect("/login");

  const configs = db.prepare("SELECT * FROM model_configs WHERE user_id = ? ORDER BY name").all(s.user.id).map(toPublic);
  return <Wizard name={name.trim()} template={t} configs={configs} locked={!s.dek} />;
}
