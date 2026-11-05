import { mkdirSync } from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";

// One SQLite file per install (local-first, PLAN 3). `data/` is git-ignored.
// A function so the provider migration below can create the same table under a temporary name.
const MODEL_CONFIGS = (name: string) => `
CREATE TABLE IF NOT EXISTS ${name} (
  id              INTEGER PRIMARY KEY,
  user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  provider        TEXT NOT NULL CHECK (provider IN ('openai', 'openrouter', 'local', 'openai_compatible')),  -- local = any self-hosted OpenAI-compatible server
  base_url        TEXT NOT NULL,
  model           TEXT NOT NULL,
  api_key_enc     BLOB,                    -- AES-256-GCM under the user's data key; NULL = no key (most self-hosted servers)
  api_key_hint    TEXT,                    -- last 4 characters, shown as "…abcd"
  temperature     REAL DEFAULT 0 CHECK (temperature BETWEEN 0 AND 2),  -- NULL = provider default
  top_p           REAL CHECK (top_p BETWEEN 0 AND 1),
  max_tokens      INTEGER CHECK (max_tokens > 0),
  seed            INTEGER,
  request_timeout REAL CHECK (request_timeout > 0),                   -- seconds
  max_retries     INTEGER NOT NULL DEFAULT 2 CHECK (max_retries BETWEEN 0 AND 10),
  verify_ssl      INTEGER NOT NULL DEFAULT 1 CHECK (verify_ssl IN (0, 1)),
  tested_at       TEXT,                    -- last "Test connection" run; cleared when endpoint, model or key change
  test_ok         INTEGER CHECK (test_ok IN (0, 1)),
  test_message    TEXT,                    -- short reply or plain-language error shown in the UI
  test_latency_ms INTEGER,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (user_id, name)
);`;

const SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,             -- scrypt$salt$hash, login check only
  key_source    TEXT NOT NULL DEFAULT 'password' CHECK (key_source IN ('password', 'custom')),
  kdf_salt      BLOB NOT NULL,             -- salt for the key-encryption key; never the password_hash salt
  wrapped_dek   BLOB NOT NULL,             -- the user's data key, sealed with scrypt(password or custom key, kdf_salt)
  recovery_salt        BLOB,             -- salt for the recovery-phrase key
  recovery_wrapped_dek BLOB,             -- the same data key, sealed with scrypt(recovery phrase); lets a reset keep API keys
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
  id         TEXT PRIMARY KEY,             -- sha256 of the cookie token, so a leaked DB can't be replayed as cookies
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL
);

${MODEL_CONFIGS("model_configs")}
`;

function open() {
  const dir = path.join(process.cwd(), "data");
  mkdirSync(dir, { recursive: true });
  const db = new DatabaseSync(path.join(dir, "app.db"));
  db.exec("PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;");
  db.exec(SCHEMA);
  return db;
}

// Reuse one connection across dev hot reloads.
const g = globalThis as { db?: DatabaseSync };
export const db = (g.db ??= open());

// Bring older databases up to the schema above. Runs on every load (cheap) so a reused dev connection migrates too.
const columns = (table: string) => (db.prepare(`PRAGMA table_info(${table})`).all() as { name: string }[]).map((c) => c.name);
if (!columns("users").includes("recovery_salt")) db.exec("ALTER TABLE users ADD COLUMN recovery_salt BLOB; ALTER TABLE users ADD COLUMN recovery_wrapped_dek BLOB;");
const mc = columns("model_configs");
if (!mc.includes("tested_at"))
  db.exec(`ALTER TABLE model_configs ADD COLUMN tested_at TEXT;
    ALTER TABLE model_configs ADD COLUMN test_ok INTEGER CHECK (test_ok IN (0, 1));
    ALTER TABLE model_configs ADD COLUMN test_message TEXT;
    ALTER TABLE model_configs ADD COLUMN test_latency_ms INTEGER;`);
// The per-template model check was dropped for a plain connection test.
if (mc.includes("capability_tier")) db.exec("ALTER TABLE model_configs DROP COLUMN capability_tier; ALTER TABLE model_configs DROP COLUMN probed_at;");
// Agents always run as ReAct, so the per-model agent mode is gone. Before the rebuild below, so its columns line up.
if (mc.includes("agent_mode")) db.exec("ALTER TABLE model_configs DROP COLUMN agent_mode;");

// 'ollama' became 'local' (Ollama, LM Studio, llama.cpp, vLLM: all OpenAI-compatible). SQLite can't change a CHECK
// in place, so copy the rows into a fresh table. Runs after the column migrations above, so the columns line up.
const ddl = (db.prepare("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'model_configs'").get() as { sql: string }).sql;
if (ddl.includes("'ollama'")) {
  const cols = columns("model_configs");
  const select = cols.map((c) => (c === "provider" ? "CASE provider WHEN 'ollama' THEN 'local' ELSE provider END" : c)).join(", ");
  db.exec("PRAGMA foreign_keys = OFF");
  db.exec(`BEGIN;
    ${MODEL_CONFIGS("model_configs_new")};
    INSERT INTO model_configs_new (${cols.join(", ")}) SELECT ${select} FROM model_configs;
    DROP TABLE model_configs;
    ALTER TABLE model_configs_new RENAME TO model_configs;
    COMMIT;`);
  db.exec("PRAGMA foreign_keys = ON");
}
