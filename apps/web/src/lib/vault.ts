// Checks for the vault endpoint the SDK server calls (PLAN 16.13). Server only. No imports from the app, so
// `npm test` can load it directly.
import { timingSafeEqual } from "node:crypto";

// `GET /api/internal/secrets/<name>`: the only names we serve are `modelcfg/<id>/api_key`.
export function configIdOf(name: string): number | null {
  const m = /^modelcfg\/([1-9][0-9]{0,9})\/api_key$/.exec(name);
  return m ? Number(m[1]) : null;
}

// Constant-time token check (an attacker learns nothing from how long a wrong guess took).
export function sameToken(given: string | null, expected: string | undefined): boolean {
  if (!given || !expected) return false;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

// Requests to the vault must come over loopback (`ab ui` binds the web app to 127.0.0.1); the Host header also
// blocks DNS rebinding, like the SDK server does.
export const isLoopbackHost = (host: string | null) => ["127.0.0.1", "localhost", "[::1]"].includes((host ?? "").replace(/:\d+$/, ""));
