import Link from "next/link";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { logout } from "../actions";

// Per-user layout: block on the session read instead of a static shell.
export const instant = false;

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();
  if (!session) redirect("/login");

  return (
    <div className="flex flex-1 flex-col bg-zinc-50 dark:bg-zinc-950">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-3 dark:border-zinc-800 dark:bg-zinc-900">
        <Link href="/dashboard" className="font-semibold">Agent Builder</Link>
        <div className="flex items-center gap-4 text-sm">
          <Link href="/dashboard/settings" className="hover:underline">Settings</Link>
          <span className="text-zinc-500">{session.user.email}</span>
          <form action={logout}>
            <button className="rounded-md border border-zinc-300 px-3 py-1 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800">
              Sign out
            </button>
          </form>
        </div>
      </header>
      {children}
    </div>
  );
}
