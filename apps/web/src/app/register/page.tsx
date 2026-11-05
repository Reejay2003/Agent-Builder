import { redirect } from "next/navigation";
import { connection } from "next/server";
import { db } from "@/lib/db";
import { AuthForm } from "../login/auth-form";

// Reads the database on each request, so it blocks instead of prerendering.
export const instant = false;

// Single-user install: setup is only open until the first account exists.
export default async function RegisterPage() {
  await connection(); // the account check must run per request, not at build time
  if (db.prepare("SELECT 1 FROM users LIMIT 1").get()) redirect("/login");
  return <AuthForm mode="register" />;
}
