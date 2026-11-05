import { redirect } from "next/navigation";
import { db } from "@/lib/db";
import { getSession } from "@/lib/session";
import { AuthForm } from "./auth-form";

// Reads the session cookie, so it blocks instead of prerendering.
export const instant = false;

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ reset?: string }> }) {
  if (await getSession()) redirect("/dashboard");
  // Single-user install: until the account exists, the only way in is setup.
  if (!db.prepare("SELECT 1 FROM users LIMIT 1").get()) redirect("/register");
  const { reset } = await searchParams;
  return <AuthForm mode="login" notice={reset ? "Password reset. Sign in with your new password." : undefined} />;
}
