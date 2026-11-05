"use client";

import { Eye, EyeOff } from "lucide-react";
import Link from "next/link";
import { useActionState, useState } from "react";
import { login, register, resetPassword } from "../actions";

const input =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 focus:ring-1 focus:ring-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:focus:border-zinc-100 dark:focus:ring-zinc-100";
const primary =
  "w-full rounded-md bg-zinc-900 py-2 text-center text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300";
const card = "w-full max-w-sm space-y-5 rounded-xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-900";

const MODES = {
  login: { action: login, title: "Agent Builder", sub: "Sign in to build and test your agents.", submit: "Sign in", pending: "Signing in…" },
  register: { action: register, title: "Set up Agent Builder", sub: "Create the account for this install. Your password also unlocks the API keys you save.", submit: "Create account", pending: "Creating account…" },
  forgot: { action: resetPassword, title: "Reset your password", sub: "Use the recovery phrase you saved when you set up this install. Your saved API keys are kept.", submit: "Reset password", pending: "Resetting…" },
};

function Field({ label, hint, ...props }: { label: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false);
  const isPassword = props.type === "password";
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      <span className="relative block">
        <input required className={input} {...props} type={isPassword && show ? "text" : props.type} style={isPassword ? { paddingRight: "2.5rem" } : undefined} />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            aria-label={show ? "Hide password" : "Show password"}
            aria-pressed={show}
            className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        )}
      </span>
      {hint && <span className="block text-xs text-zinc-500">{hint}</span>}
    </label>
  );
}

export function AuthForm({ mode, notice }: { mode: keyof typeof MODES; notice?: string }) {
  const m = MODES[mode];
  const [state, action, pending] = useActionState(m.action, undefined);

  if (state?.phrase) return <PhraseScreen phrase={state.phrase} />;

  return (
    <main className="flex flex-1 items-center justify-center bg-zinc-50 px-4 dark:bg-zinc-950">
      <form action={action} className={card}>
        <div>
          <h1 className="text-xl font-semibold">{m.title}</h1>
          <p className="mt-1 text-sm text-zinc-500">{m.sub}</p>
        </div>
        {notice && <p role="status" className="text-sm text-green-600">{notice}</p>}

        <Field label="Email" name="email" type="email" autoComplete="email" />
        {mode === "forgot" && <Field label="Recovery phrase" name="phrase" autoComplete="off" spellCheck={false} placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX" className={`${input} font-mono`} />}
        {mode === "login" ? (
          <Field label="Password" name="password" type="password" autoComplete="current-password" />
        ) : (
          <>
            <Field label={mode === "forgot" ? "New password" : "Password"} name="password" type="password" autoComplete="new-password" minLength={8} hint="At least 8 characters." />
            <Field label="Confirm password" name="confirm" type="password" autoComplete="new-password" minLength={8} />
          </>
        )}

        {state?.error && <p role="alert" className="text-sm text-red-600">{state.error}</p>}
        <button disabled={pending} className={primary}>{pending ? m.pending : m.submit}</button>

        {mode === "login" && (
          <p className="text-center text-sm">
            <Link href="/forgot" className="text-zinc-500 hover:underline">Forgot password?</Link>
          </p>
        )}
        {mode === "forgot" && (
          <p className="text-center text-sm">
            <Link href="/login" className="text-zinc-500 hover:underline">Back to sign in</Link>
          </p>
        )}
      </form>
    </main>
  );
}

// Shown once, right after registration. The phrase is never stored in plain text and can't be shown again.
function PhraseScreen({ phrase }: { phrase: string }) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  return (
    <main className="flex flex-1 items-center justify-center bg-zinc-50 px-4 dark:bg-zinc-950">
      <div className={card}>
        <div>
          <h1 className="text-xl font-semibold">Save your recovery phrase</h1>
          <p className="mt-1 text-sm text-zinc-500">
            It's the only way to reset a forgotten password without losing your saved API keys. Anyone with it can reset your password, so keep it somewhere private, like a password manager. It won't be shown again.
          </p>
        </div>
        <p className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-center font-mono text-base tracking-wide whitespace-nowrap select-all dark:border-zinc-800 dark:bg-zinc-950">{phrase}</p>
        <button
          type="button"
          className="w-full rounded-md border border-zinc-300 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          onClick={() => navigator.clipboard.writeText(phrase).then(() => setCopied(true))}
        >
          {copied ? "Copied" : "Copy phrase"}
        </button>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-0.5 size-4" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
          I've saved my recovery phrase somewhere safe.
        </label>
        {saved ? (
          <Link href="/login" className={`block ${primary}`}>Continue to sign in</Link>
        ) : (
          <button disabled className={primary}>Continue to sign in</button>
        )}
      </div>
    </main>
  );
}
