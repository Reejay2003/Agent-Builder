import { createCipheriv, createDecipheriv, randomBytes, scryptSync, timingSafeEqual } from "node:crypto";

// scrypt N=2^15, r=8: ~32 MB and tens of ms per call, so maxmem must exceed the 32 MB default.
const SCRYPT = { N: 1 << 15, r: 8, p: 1, maxmem: 64 * 1024 * 1024 };

export const randomKey = () => randomBytes(32);
export const randomSalt = () => randomBytes(16);

// Key-encryption key from a password or a user-chosen key. Use a salt that is not the password_hash salt.
export function deriveKey(secret: string, salt: Uint8Array): Buffer {
  return scryptSync(secret.normalize("NFKC"), salt, 32, SCRYPT);
}

export function hashPassword(password: string): string {
  const salt = randomSalt();
  return `scrypt$${salt.toString("base64")}$${deriveKey(password, salt).toString("base64")}`;
}

export function verifyPassword(password: string, stored: string): boolean {
  const [scheme, salt, hash] = stored.split("$");
  if (scheme !== "scrypt" || !salt || !hash) return false;
  const expected = Buffer.from(hash, "base64");
  const actual = deriveKey(password, Buffer.from(salt, "base64"));
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

// AES-256-GCM. Blob layout: iv (12) | tag (16) | ciphertext. `aad` binds the blob to its purpose and owner.
export function seal(key: Uint8Array, plaintext: Uint8Array, aad: string): Buffer {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv).setAAD(Buffer.from(aad));
  const ct = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), ct]);
}

// Throws on a wrong key, wrong aad or tampered blob.
export function open(key: Uint8Array, blob: Uint8Array, aad: string): Buffer {
  const b = Buffer.from(blob);
  const decipher = createDecipheriv("aes-256-gcm", key, b.subarray(0, 12)).setAAD(Buffer.from(aad));
  decipher.setAuthTag(b.subarray(12, 28));
  return Buffer.concat([decipher.update(b.subarray(28)), decipher.final()]);
}

// Recovery phrase: 6 groups of 4 from a 32-symbol alphabet (no I, L, O, U) = 120 random bits.
// 256 is a multiple of 32, so `byte & 31` stays uniform.
const ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ0123456789";
export function recoveryPhrase(): string {
  const b = randomBytes(24);
  return Array.from({ length: 6 }, (_, g) => Array.from(b.subarray(g * 4, g * 4 + 4), (x) => ALPHABET[x & 31]).join("")).join("-");
}
// Accept any case, spaces or dashes when the user types it back.
export const normalizePhrase = (p: string) => p.toUpperCase().replace(/[^A-Z0-9]/g, "");
