"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { deriveKey, hashPassword, normalizePhrase, open, randomKey, randomSalt, recoveryPhrase, seal, verifyPassword } from "@/lib/crypto";
import { db } from "@/lib/db";
import { endSession, getSession, setDataKey, startSession, type User } from "@/lib/session";

// The user's data key (which seals their API keys) is wrapped by a key derived from this secret.
const wrap = (secret: string, dek: Buffer, aad = "dek") => {
  const salt = randomSalt();
  return { kdf_salt: salt, wrapped_dek: seal(deriveKey(secret, salt), dek, aad) };
};
const RECOVERY = "dek-recovery";

const EMAIL = /^\S+@\S+\.\S+$/;
export type AuthState = { error?: string; phrase?: string } | undefined;
const hasAccount = () => !!db.prepare("SELECT 1 FROM users LIMIT 1").get();

export async function login(_prev: AuthState, formData: FormData): Promise<AuthState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!EMAIL.test(email)) return { error: "Enter a valid email." };
  if (!password) return { error: "Enter your password." };

  const user = db.prepare("SELECT * FROM users WHERE email = ?").get(email) as User | undefined;
  if (!user || !verifyPassword(password, user.password_hash)) return { error: "Wrong email or password." };
  // With a custom key the session starts locked until the user enters that key in Settings.
  const dek = user.key_source === "password" ? open(deriveKey(password, user.kdf_salt), user.wrapped_dek, "dek") : null;
  await startSession(user.id, dek);
  redirect("/dashboard");
}

// Single-user install: registration works only until the first account exists.
// Returns the recovery phrase to show once; the user then signs in.
export async function register(_prev: AuthState, formData: FormData): Promise<AuthState> {
  if (hasAccount()) return { error: "This install already has an account. Sign in instead." };
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!EMAIL.test(email)) return { error: "Enter a valid email." };
  if (password.length < 8) return { error: "Use at least 8 characters." };
  if (password !== formData.get("confirm")) return { error: "The passwords don't match." };

  // One data key seals the API keys; the password and the recovery phrase each wrap a copy of it.
  const dek = randomKey();
  const phrase = recoveryPhrase();
  const w = wrap(password, dek);
  const r = wrap(normalizePhrase(phrase), dek, RECOVERY);
  db.prepare("INSERT INTO users (email, password_hash, kdf_salt, wrapped_dek, recovery_salt, recovery_wrapped_dek) VALUES (?, ?, ?, ?, ?, ?)")
    .run(email, hashPassword(password), w.kdf_salt, w.wrapped_dek, r.kdf_salt, r.wrapped_dek);
  return { phrase };
}

// Forgot password: the recovery phrase unwraps the data key, so saved API keys survive the reset.
// The encryption key goes back to the (new) login password, and every session is signed out.
export async function resetPassword(_prev: AuthState, formData: FormData): Promise<AuthState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (password.length < 8) return { error: "Use at least 8 characters." };
  if (password !== formData.get("confirm")) return { error: "The passwords don't match." };

  const user = db.prepare("SELECT * FROM users WHERE email = ?").get(email) as User | undefined;
  let dek: Buffer;
  // An unknown email or a pre-recovery account throws here too, so every failure gets the same answer.
  try {
    dek = open(deriveKey(normalizePhrase(String(formData.get("phrase") ?? "")), user!.recovery_salt!), user!.recovery_wrapped_dek!, RECOVERY);
  } catch {
    return { error: "That email and recovery phrase don't match." };
  }
  const w = wrap(password, dek);
  db.prepare("UPDATE users SET password_hash = ?, key_source = 'password', kdf_salt = ?, wrapped_dek = ? WHERE id = ?")
    .run(hashPassword(password), w.kdf_salt, w.wrapped_dek, user!.id);
  db.prepare("DELETE FROM sessions WHERE user_id = ?").run(user!.id);
  redirect("/login?reset=1");
}

export async function logout() {
  await endSession();
  redirect("/login");
}

type KeyState = { error?: string; ok?: string } | undefined;

// Unlock the data key for this session with the current secret (password or custom key).
export async function unlock(_prev: KeyState, formData: FormData): Promise<KeyState> {
  const s = await getSession();
  if (!s) redirect("/login");
  try {
    setDataKey(s.id, open(deriveKey(String(formData.get("secret") ?? ""), s.user.kdf_salt), s.user.wrapped_dek, "dek"));
  } catch {
    return { error: s.user.key_source === "password" ? "Wrong password." : "That key doesn't match." };
  }
  return { ok: "Unlocked." };
}

// Switch between the login password and a custom key. Only the data key is re-wrapped;
// stored API keys stay as they are.
export async function setKeySource(_prev: KeyState, formData: FormData): Promise<KeyState> {
  const s = await getSession();
  if (!s) redirect("/login");
  if (!s.dek) return { error: "Unlock first." };
  const source = formData.get("source");
  const secret = String(formData.get("secret") ?? "");
  if (source === "password") {
    if (!verifyPassword(secret, s.user.password_hash)) return { error: "Wrong password." };
  } else if (source === "custom") {
    if (secret.length < 12) return { error: "Use at least 12 characters." };
    if (secret !== formData.get("confirm")) return { error: "The two keys don't match." };
  } else return { error: "Pick a key source." };

  const w = wrap(secret, s.dek);
  db.prepare("UPDATE users SET key_source = ?, kdf_salt = ?, wrapped_dek = ? WHERE id = ?").run(source, w.kdf_salt, w.wrapped_dek, s.user.id);
  revalidatePath("/dashboard/settings");
  return { ok: source === "password" ? "Now using your login password." : "Now using your own key. Keep it safe: it can't be recovered." };
}

// ponytail: mock create, nothing is stored and the dashboard list stays the fixed mock.
// Persist the `spec` field (AgentSpec YAML from the wizard) through the control service (PLAN P1.6).
export async function createAgent(formData: FormData) {
  const name = String(formData.get("name") ?? "").trim();
  if (!name || !formData.get("template")) return;
  redirect("/dashboard");
}
