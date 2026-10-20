"use client";

import { useActionState, useState } from "react";
import { setKeySource, unlock } from "../../actions";

const input =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 focus:ring-1 focus:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:focus:border-zinc-100 dark:focus:ring-zinc-100";
const card = "space-y-4 rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900";
const primary =
  "rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300";

function Status({ state }: { state: { error?: string; ok?: string } | undefined }) {
  if (state?.error) return <p role="alert" className="text-sm text-red-600">{state.error}</p>;
  if (state?.ok) return <p role="status" className="text-sm text-green-600">{state.ok}</p>;
  return null;
}

export function KeyForms({ source, locked }: { source: "password" | "custom"; locked: boolean }) {
  const [unlockState, unlockAction, unlocking] = useActionState(unlock, undefined);
  const [sourceState, sourceAction, saving] = useActionState(setKeySource, undefined);
  const [pick, setPick] = useState(source);
  const isLocked = locked && !unlockState?.ok;

  return (
    <>
      {isLocked && (
        <form action={unlockAction} className={`${card} border-amber-300 dark:border-amber-800`}>
          <div>
            <h2 className="font-medium">Encryption key locked</h2>
            <p className="mt-1 text-sm text-zinc-500">
              {source === "password"
                ? "The server restarted since you signed in. Enter your password to unlock your saved API keys."
                : "Enter your encryption key to save or use API keys in this session."}
            </p>
          </div>
          <input name="secret" type="password" required autoComplete={source === "password" ? "current-password" : "off"} className={input} />
          <Status state={unlockState} />
          <button disabled={unlocking} className={primary}>{unlocking ? "Unlocking…" : "Unlock"}</button>
        </form>
      )}

      {/* React resets the form after each action; keep the shown fields in step with the radios. */}
      <form action={sourceAction} onReset={() => setPick(source)} className={card}>
        <div>
          <h2 className="font-medium">Encryption key</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Currently: <strong>{source === "password" ? "your login password" : "your own key"}</strong>. Switching keeps your saved API keys.
          </p>
        </div>
        <fieldset className="space-y-2">
          {(["password", "custom"] as const).map((v) => (
            <label key={v} className="flex items-start gap-2 text-sm">
              <input type="radio" name="source" value={v} defaultChecked={source === v} onChange={() => setPick(v)} className="mt-1" />
              <span>
                <span className="font-medium">{v === "password" ? "Login password" : "My own key"}</span>
                <span className="block text-zinc-500">
                  {v === "password"
                    ? "Unlocked automatically when you sign in."
                    : "A separate passphrase you enter after each sign-in. If you lose it, saved API keys must be re-entered."}
                </span>
              </span>
            </label>
          ))}
        </fieldset>
        <label className="block space-y-1.5">
          <span className="block text-sm font-medium">{pick === "password" ? "Confirm your login password" : "New key (12+ characters)"}</span>
          <input name="secret" type="password" required autoComplete={pick === "password" ? "current-password" : "new-password"} className={input} />
        </label>
        {pick === "custom" && (
          <label className="block space-y-1.5">
            <span className="block text-sm font-medium">Repeat the key</span>
            <input name="confirm" type="password" required autoComplete="new-password" className={input} />
          </label>
        )}
        <Status state={sourceState} />
        <button disabled={saving || isLocked} className={primary}>{saving ? "Saving…" : "Save"}</button>
      </form>
    </>
  );
}
