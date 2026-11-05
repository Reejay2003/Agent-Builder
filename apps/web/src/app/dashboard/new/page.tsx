import Link from "next/link";
import { templates } from "./templates";

// Session read in the layout blocks; opt the page out too or sibling navigation is flagged.
export const instant = false;

const input =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 focus:ring-1 focus:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:focus:border-zinc-100 dark:focus:ring-zinc-100";

export default function NewAgent() {
  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 px-6 py-8">
      <div>
        <Link href="/dashboard" className="text-sm text-zinc-500 hover:underline">← Back to agents</Link>
        <h1 className="mt-2 text-2xl font-semibold">New agent</h1>
        <p className="mt-1 text-sm text-zinc-500">Name it and pick what kind of agent it is. Tools, connections and testing come next.</p>
      </div>

      <form action="/dashboard/new/setup" className="space-y-6">
        <label className="block max-w-sm space-y-1.5">
          <span className="text-sm font-medium">Name</span>
          <input name="name" required maxLength={60} placeholder="e.g. Daily brief" className={input} />
        </label>

        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">Agent type</legend>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {templates.map((t, i) => (
              <label
                key={t.id}
                className="relative flex cursor-pointer flex-col gap-2 rounded-xl border border-zinc-200 bg-white p-4 has-checked:border-zinc-900 has-checked:ring-1 has-checked:ring-zinc-900 has-disabled:cursor-not-allowed has-disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900 dark:has-checked:border-zinc-100 dark:has-checked:ring-zinc-100"
              >
                <input type="radio" name="template" value={t.id} required defaultChecked={i === 0} disabled={!t.ready} className="sr-only" />
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{t.name}</span>
                  {!t.ready && <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">Coming soon</span>}
                </div>
                <p className="text-sm text-zinc-600 dark:text-zinc-400">{t.desc}</p>
                <p className="mt-auto text-xs text-zinc-500">{t.tools}</p>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="flex justify-end gap-3">
          <Link href="/dashboard" className="rounded-md border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800">
            Cancel
          </Link>
          <button className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300">
            Next: set up
          </button>
        </div>
      </form>
    </main>
  );
}
