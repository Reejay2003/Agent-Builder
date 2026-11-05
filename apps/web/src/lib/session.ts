import { createHash, randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { db } from "./db";

export type User = {
  id: number;
  email: string;
  password_hash: string;
  key_source: "password" | "custom";
  kdf_salt: Uint8Array;
  wrapped_dek: Uint8Array;
  recovery_salt: Uint8Array | null;
  recovery_wrapped_dek: Uint8Array | null;
};

const DAYS = 7;
const hash = (token: string) => createHash("sha256").update(token).digest("hex");

// ponytail: unwrapped data keys live only in this process's memory. A server restart locks every
// session until the user re-enters their password or key; persist nothing here.
const g = globalThis as { dataKeys?: Map<string, Buffer> };
const dataKeys = (g.dataKeys ??= new Map());

export async function startSession(userId: number, dek: Buffer | null) {
  const token = randomBytes(32).toString("base64url");
  const id = hash(token);
  db.prepare("INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, datetime('now', ?))").run(id, userId, `+${DAYS} days`);
  if (dek) dataKeys.set(id, dek);
  (await cookies()).set("session", token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: DAYS * 86400,
  });
}

// The signed-in user, plus their data key when it is unlocked in this process.
export async function getSession() {
  const token = (await cookies()).get("session")?.value;
  if (!token) return null;
  const id = hash(token);
  const user = db
    .prepare("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = ? AND s.expires_at > datetime('now')")
    .get(id) as User | undefined;
  if (!user) return null;
  return { id, user, dek: dataKeys.get(id) as Buffer | undefined };
}

export function setDataKey(sessionId: string, dek: Buffer) {
  dataKeys.set(sessionId, dek);
}

export async function endSession() {
  const store = await cookies();
  const token = store.get("session")?.value;
  if (token) {
    const id = hash(token);
    db.prepare("DELETE FROM sessions WHERE id = ?").run(id);
    dataKeys.delete(id);
  }
  store.delete("session");
}
