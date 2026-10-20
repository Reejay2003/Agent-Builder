import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { KeyForms } from "./key-forms";

// Session read in the layout blocks; opt the page out too or sibling navigation is flagged.
export const instant = false;

export default async function Settings() {
  const s = await getSession();
  if (!s) redirect("/login");
  return (
    <main className="mx-auto w-full max-w-2xl space-y-6 px-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Your model API keys are encrypted with a key that only you can unlock: your login password, or a key you choose.
        </p>
      </div>
      <KeyForms key={s.user.key_source} source={s.user.key_source} locked={!s.dek} />
    </main>
  );
}
