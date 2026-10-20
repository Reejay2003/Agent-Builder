import Link from "next/link";

// Session read in the layout blocks; opt the page out too or sibling navigation is flagged.
export const instant = false;

// Mock data until the control service exists (PLAN P1.6).
const agents = [
  { name: "Daily brief", template: "Personal automation", model: "gpt-4.1-mini", mode: "tool_calling", status: "Published", lastRun: "Today 08:00" },
  { name: "Inbox triage", template: "Personal automation", model: "gpt-4.1-mini", mode: "tool_calling", status: "Testing", lastRun: "Yesterday" },
  { name: "Wiki researcher", template: "Research / analyst", model: "nemotron-3-nano-4b", mode: "react", status: "Draft", lastRun: "Never" },
];

const stats = [
  { label: "Agents", value: agents.length },
  { label: "Runs today", value: 14 },
  { label: "Pending approvals", value: 2 },
];

const badge: Record<string, string> = {
  Published: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  Testing: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  Draft: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

export default function Dashboard() {
  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Your agents</h1>
        <Link
          href="/dashboard/new"
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          + New agent
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {stats.map((s) => (
          <div key={s.label} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
            <p className="text-sm text-zinc-500">{s.label}</p>
            <p className="mt-1 text-2xl font-semibold">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-200 text-zinc-500 dark:border-zinc-800">
            <tr>
              {["Name", "Template", "Model", "Mode", "Status", "Last run"].map((h) => (
                <th key={h} className="px-4 py-3 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.name} className="border-b border-zinc-100 last:border-0 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50">
                <td className="px-4 py-3 font-medium">{a.name}</td>
                <td className="px-4 py-3">{a.template}</td>
                <td className="px-4 py-3 font-mono text-xs">{a.model}</td>
                <td className="px-4 py-3 font-mono text-xs">{a.mode}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge[a.status]}`}>{a.status}</span>
                </td>
                <td className="px-4 py-3 text-zinc-500">{a.lastRun}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
