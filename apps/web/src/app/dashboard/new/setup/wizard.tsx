"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { buildSpec, type AgentMode } from "@/lib/agent-spec";
import type { ModelConfig } from "@/lib/model-configs";
import { createAgent } from "../../../actions";
import { templates } from "../templates";

type Template = (typeof templates)[number];

// Wizard steps from PLAN 2; `phase` marks steps not built yet (greyed in the rail).
const steps = [
  { name: "Model" },
  { name: "Type" },
  { name: "Tools" },
  { name: "Connect", phase: 3 },
  { name: "Knowledge", phase: 4 },
  { name: "Configure" },
  { name: "Test" },
  { name: "Evaluate", phase: 5 },
  { name: "Publish", phase: 5 },
];
const active = steps.flatMap((s, i) => (s.phase ? [] : [i]));

const providers = [
  { id: "openai", label: "OpenAI", url: "https://api.openai.com/v1" },
  { id: "openrouter", label: "OpenRouter", url: "https://openrouter.ai/api/v1" },
  { id: "local", label: "Self-hosted (Ollama, LM Studio, llama.cpp, vLLM)", url: "http://localhost:11434/v1" },
  { id: "openai_compatible", label: "Other OpenAI-compatible URL", url: "" },
] as const;
// Default ports of the common self-hosted servers; all serve the OpenAI API under /v1.
const localServers = [
  { label: "Ollama", url: "http://localhost:11434/v1" },
  { label: "LM Studio", url: "http://localhost:1234/v1" },
  { label: "llama.cpp", url: "http://localhost:8080/v1" },
  { label: "vLLM", url: "http://localhost:8000/v1" },
];

// Editable copy of a model config. Numbers stay strings while typing; "" means "provider default".
type Draft = Omit<ModelConfig, "id" | "temperature" | "top_p" | "max_tokens" | "seed" | "request_timeout" | "max_retries" | "updated_at"> & {
  id: number | null;
  temperature: string;
  top_p: string;
  max_tokens: string;
  seed: string;
  request_timeout: string;
  max_retries: string;
  api_key: string; // typed but unsaved; never filled from the server
  remove_key: boolean;
};
const str = (v: number | null) => (v === null ? "" : String(v));
const toDraft = (c?: ModelConfig): Draft =>
  c
    ? { ...c, temperature: str(c.temperature), top_p: str(c.top_p), max_tokens: str(c.max_tokens), seed: str(c.seed), request_timeout: str(c.request_timeout), max_retries: str(c.max_retries), api_key: "", remove_key: false }
    : { id: null, name: "", provider: "openai", base_url: providers[0].url, model: "gpt-4.1-mini", temperature: "0", top_p: "", max_tokens: "", seed: "", request_timeout: "", max_retries: "2", verify_ssl: true, has_api_key: false, api_key_hint: null, tested_at: null, test_ok: null, test_message: null, test_latency_ms: null, api_key: "", remove_key: false };
const num = (v: string) => (v.trim() === "" ? null : Number(v));

// fetch that never throws: a dead app server, a crashed route (empty 500) or a non-JSON body all
// become one readable message instead of an unhandled rejection.
async function api<T>(url: string, init?: RequestInit): Promise<{ ok: true; data: T } | { ok: false; error: string }> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    return { ok: false, error: "Can't reach the Agent Builder server. Is it still running?" };
  }
  const data = await res.json().catch(() => null);
  if (res.ok) return { ok: true, data: data as T };
  // Two error shapes: the web app's { error } and the SDK's { errors: [{ field, message }] }.
  const sdkError = Array.isArray(data?.errors) ? data.errors.map((e: { message?: string }) => e.message).filter(Boolean).join(" · ") : "";
  return { ok: false, error: data?.error ?? (sdkError || `Something went wrong on the server (HTTP ${res.status}). Check the server log.`) };
}
const json = (method: string, body: object): RequestInit => ({ method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
const tierChip = [
  ["Tier 0 · read only", "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"],
  ["Tier 1 · drafts", "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300"],
  ["Tier 2 · changes things", "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"],
  ["Tier 3 · high risk", "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"],
];

const input =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 focus:ring-1 focus:ring-zinc-900 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:focus:border-zinc-100 dark:focus:ring-zinc-100";
// Match the text inputs: same border, padding and height as `input`.
const trigger = `${input} data-[size=default]:h-auto`;
const primary =
  "rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300";
const secondary = "rounded-md border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 disabled:opacity-40 dark:border-zinc-700 dark:hover:bg-zinc-800";

type SdkTool = { id: string; description: string; risk_tier: number; side_effects: string; egress_hosts: string[] };

type WizardProps = { name: string; template: Template; configs: ModelConfig[]; locked: boolean };

export function Wizard({ name: initialName, template: initial, configs: initialConfigs, locked }: WizardProps) {
  const [name, setName] = useState(initialName);
  const [template, setTemplate] = useState(initial);
  const [step, setStep] = useState(0);
  const [done, setDone] = useState(new Set([1]));
  const [showSpec, setShowSpec] = useState(true);
  const [configs, setConfigs] = useState(initialConfigs);
  const [draft, setDraft] = useState(toDraft(initialConfigs[0]));
  const [tools, setTools] = useState(new Set<string>(template.recommended ?? []));
  const [basket, setBasket] = useState<{ tools?: SdkTool[]; error?: string }>({});
  const [agentMode, setAgentMode] = useState<AgentMode>("auto");
  const [check, setCheck] = useState<{ yaml?: string; warnings?: string[]; error?: string }>({});
  const [persona, setPersona] = useState(template.instructions ?? "");
  const [rules, setRules] = useState("Never send, delete or pay for anything without asking me.");
  const [guard, setGuard] = useState("standard");

  // The spec is plain JSON; the SDK validates it and writes the YAML (PLAN 16.13). The model section is filled in on
  // the server from the saved config, so the browser never decides where the key is sent.
  const spec = buildSpec({ name, type: template.id, model: null, persona, rules, tools: [...tools], guardrails: guard });
  const specJson = JSON.stringify(spec);
  const request = { spec, config_id: draft.id, agent_mode: agentMode };

  useEffect(() => {
    api<{ tools: SdkTool[] }>("/api/sdk/tools").then((r) => setBasket(r.ok ? { tools: r.data.tools } : { error: r.error }));
  }, []);
  // Re-validate (debounced) whenever the spec changes; the side panel shows exactly what the SDK will run.
  useEffect(() => {
    if (!draft.id) return setCheck({ error: "Save a model config (step 1) to see the spec the SDK writes." });
    const t = setTimeout(async () => {
      const r = await api<{ spec_yaml: string; warnings: string[] }>("/api/sdk/validate", json("POST", { spec: JSON.parse(specJson), config_id: draft.id, agent_mode: agentMode }));
      setCheck(r.ok ? { yaml: r.data.spec_yaml, warnings: r.data.warnings } : { error: r.error });
    }, 400);
    return () => clearTimeout(t);
  }, [specJson, draft.id, agentMode]);

  // A new type brings its own recommended tools and default persona.
  const pickTemplate = (t: Template) => {
    setTemplate(t);
    setTools(new Set(t.recommended ?? []));
    setPersona(t.instructions ?? "");
  };

  const pos = active.indexOf(step);
  const go = (i: number) => {
    setDone((d) => new Set(d).add(step));
    setStep(i);
  };

  return (
    <div className="grid w-full flex-1 lg:grid-cols-[220px_1fr_auto]">
      <nav aria-label="Wizard steps" className="space-y-1 border-b border-zinc-200 bg-white p-4 lg:border-r lg:border-b-0 dark:border-zinc-800 dark:bg-zinc-900">
        <Link href="/dashboard" className="mb-4 block text-sm text-zinc-500 hover:underline">← Agents</Link>
        <p className="mb-3 truncate font-semibold">{name || "Untitled agent"}</p>
        <ol className="space-y-1">
          {steps.map((s, i) => {
            const clickable = active.includes(i);
            return (
              <li key={s.name}>
                <button
                  type="button"
                  disabled={!clickable}
                  onClick={() => go(i)}
                  aria-current={i === step ? "step" : undefined}
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm ${i === step ? "bg-zinc-200 font-medium dark:bg-zinc-800" : clickable ? "hover:bg-zinc-100 dark:hover:bg-zinc-900" : "text-zinc-400 dark:text-zinc-600"}`}
                >
                  <span className="w-4 text-xs text-zinc-500">{i + 1}</span>
                  <span className="flex-1">{s.name}</span>
                  {s.phase ? (
                    <span className="text-[10px] uppercase">Phase {s.phase}</span>
                  ) : done.has(i) && i !== step ? (
                    <span className="text-green-600">✓</span>
                  ) : i === step ? (
                    <span className="text-zinc-900 dark:text-zinc-100">●</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      <form action={createAgent} className="min-w-0 space-y-6 p-6">
        <input type="hidden" name="name" value={name} />
        <input type="hidden" name="template" value={template.id} />
        <input type="hidden" name="spec" value={specJson} />

        <section className="space-y-5 rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
          {step === 0 && <ModelStep configs={configs} setConfigs={setConfigs} draft={draft} setDraft={setDraft} locked={locked} agentMode={agentMode} setAgentMode={setAgentMode} />}

          {step === 1 && (
            <>
              <Heading title="Agent type" sub="Changing the type resets tools and persona to that type's defaults." />
              <Field label="Name">
                <input className={`${input} max-w-sm`} required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {templates.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    disabled={!t.ready}
                    aria-pressed={t.id === template.id}
                    onClick={() => t.id !== template.id && pickTemplate(t)}
                    className={`flex flex-col gap-1.5 rounded-xl border p-4 text-left disabled:cursor-not-allowed disabled:opacity-50 ${t.id === template.id ? "border-zinc-900 ring-1 ring-zinc-900 dark:border-zinc-100 dark:ring-zinc-100" : "border-zinc-200 hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600"}`}
                  >
                    <span className="flex items-center justify-between gap-2 font-medium">
                      {t.name}
                      {!t.ready && <span className="shrink-0 whitespace-nowrap rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-normal text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">Coming soon</span>}
                    </span>
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">{t.desc}</span>
                  </button>
                ))}
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <Heading title="Pick tools" sub="Recommended tools for this agent type are ticked. Tier 2 tools contact other people: in a live run, every call waits for you to approve it." />
              {basket.error && <p role="alert" className="text-sm text-red-600">{basket.error}</p>}
              {!basket.tools && !basket.error && <p className="text-sm text-zinc-500">Loading tools…</p>}
              <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {(basket.tools ?? []).map((t) => (
                  <label key={t.id} className="flex cursor-pointer items-center gap-3 py-3">
                    <input
                      type="checkbox"
                      className="size-4"
                      checked={tools.has(t.id)}
                      onChange={() => setTools((s) => {
                        const n = new Set(s);
                        if (!n.delete(t.id)) n.add(t.id);
                        return n;
                      })}
                    />
                    <span className="min-w-0 flex-1 text-sm">
                      {t.description}
                      <span className="ml-2 font-mono text-xs text-zinc-500">{t.id}</span>
                      {t.egress_hosts.length > 0 && <span className="block text-xs text-zinc-500">Talks to {t.egress_hosts.join(", ")}</span>}
                    </span>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${tierChip[t.risk_tier][1]}`}>{tierChip[t.risk_tier][0]}</span>
                  </label>
                ))}
              </div>
            </>
          )}

          {step === 5 && (
            <>
              <Heading title="Configure" sub="How the agent behaves. The platform safety floor is always on." />
              <Field label="Persona">
                <textarea rows={4} className={input} value={persona} onChange={(e) => setPersona(e.target.value)} />
              </Field>
              <Field label="Rules (one per line)">
                <textarea rows={4} className={input} value={rules} onChange={(e) => setRules(e.target.value)} />
              </Field>
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">Guardrail strictness</legend>
                <div className="inline-flex rounded-md border border-zinc-300 p-0.5 dark:border-zinc-700">
                  {["strict", "standard", "relaxed"].map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setGuard(g)}
                      aria-pressed={guard === g}
                      className={`rounded px-3 py-1 text-sm capitalize ${guard === g ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : ""}`}
                    >
                      {g}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-zinc-500">Floor locked: prompt-injection checks, secret redaction and approval for Tier 2+ cannot be turned off.</p>
              </fieldset>
            </>
          )}

          {step === 6 && <TestStep request={request} />}
        </section>

        <div className="flex justify-between gap-3">
          <button type="button" className={secondary} disabled={pos <= 0} onClick={() => go(active[pos - 1])}>Back</button>
          {pos < active.length - 1 ? (
            <button type="button" className={primary} onClick={() => go(active[pos + 1])}>Next</button>
          ) : (
            <button className={primary}>Create agent</button>
          )}
        </div>
      </form>

      <aside className="border-t border-zinc-200 bg-white lg:w-96 lg:border-t-0 lg:border-l dark:border-zinc-800 dark:bg-zinc-900">
        <div className="sticky top-0">
          <button
            type="button"
            onClick={() => setShowSpec((v) => !v)}
            aria-expanded={showSpec}
            className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium"
          >
            AgentSpec (checked by the SDK)
            <span className="text-zinc-500">{showSpec ? "Hide" : "Show"}</span>
          </button>
          {showSpec && (
            <div className="max-h-[calc(100vh-3rem)] space-y-3 overflow-auto border-t border-zinc-200 p-4 dark:border-zinc-800">
              {check.error && <p role="alert" className="text-xs text-red-600 [overflow-wrap:anywhere]">{check.error}</p>}
              {check.yaml && <pre className="font-mono text-xs leading-relaxed">{check.yaml}</pre>}
              {!!check.warnings?.length && (
                <ul className="space-y-1 text-xs text-amber-700 dark:text-amber-300">
                  {check.warnings.map((w) => <li key={w}>⚠ {w}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function Heading({ title, sub }: { title: string; sub: string }) {
  return (
    <div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-zinc-500">{sub}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-sm font-medium">{label}</span>
      {children}
    </label>
  );
}

function ModelStep({ configs, setConfigs, draft, setDraft, locked, agentMode, setAgentMode }: {
  configs: ModelConfig[];
  setConfigs: React.Dispatch<React.SetStateAction<ModelConfig[]>>;
  draft: Draft;
  setDraft: (d: Draft) => void;
  locked: boolean;
  agentMode: AgentMode;
  setAgentMode: (m: AgentMode) => void;
}) {
  const [probe, setProbe] = useState<{ busy?: boolean; ok?: boolean; message?: string }>({});
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [modelsMsg, setModelsMsg] = useState<{ error?: string; ok?: string }>({});
  const [msg, setMsg] = useState<{ error?: string; ok?: string }>({});
  const [confirmDelete, setConfirmDelete] = useState(false);
  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch });
  const pick = (c?: ModelConfig) => {
    setDraft(toDraft(c));
    setMsg({});
    setConfirmDelete(false);
  };

  // Returns the saved config, or null when the save was rejected.
  async function save(): Promise<ModelConfig | null> {
    setBusy(true);
    setMsg({});
    const body = {
      name: draft.name, provider: draft.provider, base_url: draft.base_url, model: draft.model,
      temperature: num(draft.temperature), top_p: num(draft.top_p), max_tokens: num(draft.max_tokens), seed: num(draft.seed),
      request_timeout: num(draft.request_timeout), max_retries: num(draft.max_retries), verify_ssl: draft.verify_ssl,
      ...(draft.api_key.trim() ? { api_key: draft.api_key } : draft.remove_key ? { api_key: null } : {}),
    };
    const r = await api<ModelConfig>(draft.id ? `/api/model-configs/${draft.id}` : "/api/model-configs", json(draft.id ? "PATCH" : "POST", body));
    setBusy(false);
    if (!r.ok) {
      setMsg({ error: r.error });
      return null;
    }
    const data = r.data;
    setConfigs(draft.id ? configs.map((c) => (c.id === data.id ? data : c)) : [...configs, data]);
    setDraft(toDraft(data));
    setMsg({ ok: "Saved." });
    return data;
  }

  // Ask the server which models it has (GET /models; free). Uses the typed key, else the saved one.
  async function loadModels() {
    setModelsMsg({ ok: "Loading…" });
    const r = await api<{ models: string[] }>(
      "/api/model-configs/discover",
      json("POST", { base_url: draft.base_url, api_key: draft.api_key || undefined, id: draft.id ?? undefined }),
    );
    if (!r.ok) {
      setModels([]);
      return setModelsMsg({ error: r.error });
    }
    const found = r.data.models;
    setModels(found);
    setModelsMsg({ ok: `${found.length} model${found.length === 1 ? "" : "s"} found. Pick one from the list.` });
    if (!draft.model) set({ model: found[0] });
  }

  // Save first so the test always runs against what's on screen, then make one real call to the provider.
  async function test() {
    const saved = await save();
    if (!saved) return;
    setTesting(true);
    setMsg({});
    const r = await api<ModelConfig>(`/api/model-configs/${saved.id}/test`, { method: "POST" });
    setTesting(false);
    if (!r.ok) return setMsg({ error: r.error });
    setConfigs((cs) => cs.map((c) => (c.id === r.data.id ? r.data : c)));
    setDraft(toDraft(r.data));
  }

  // The SDK's model check (PLAN 4.4.1): one real request that requires a tool call. Its `agent_mode` goes into the
  // spec: `auto` when the model can call tools, `react` (tools described in text) when it cannot.
  async function checkTools() {
    const saved = await save();
    if (!saved) return;
    setProbe({ busy: true });
    const r = await api<{ ok: boolean; tool_calling: boolean | null; agent_mode: AgentMode | null; message: string }>(`/api/model-configs/${saved.id}/check`, { method: "POST" });
    if (!r.ok) return setProbe({ ok: false, message: r.error });
    if (r.data.agent_mode) setAgentMode(r.data.agent_mode);
    setProbe({ ok: r.data.ok, message: r.data.message });
  }

  async function remove() {
    if (!draft.id) return;
    setBusy(true);
    const r = await api(`/api/model-configs/${draft.id}`, { method: "DELETE" });
    setBusy(false);
    if (!r.ok) return setMsg({ error: r.error });
    const rest = configs.filter((c) => c.id !== draft.id);
    setConfigs(rest);
    pick(rest[0]);
  }

  const keyPlaceholder = draft.has_api_key && !draft.remove_key
    ? `Saved (…${draft.api_key_hint}). Leave blank to keep.`
    : draft.provider === "local" ? "Usually not needed" : "sk-…";

  return (
    <>
      <Heading title="Connect your model" sub="Any OpenAI-compatible endpoint. API keys are encrypted with your key and never shown again." />
      {locked && (
        <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          Your encryption key is locked, so new API keys can't be saved. <Link href="/dashboard/settings" className="underline">Unlock in Settings</Link>.
        </p>
      )}

      {/* Only worth showing once there is something saved to pick. */}
      {configs.length > 0 && (
        <Field label="Saved model configs">
          <Select value={draft.id ? String(draft.id) : "new"} onValueChange={(v) => pick(configs.find((c) => String(c.id) === v))}>
            <SelectTrigger className={trigger}><SelectValue /></SelectTrigger>
            <SelectContent position="popper">
              {configs.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name} · {c.model}</SelectItem>)}
              <SelectItem value="new">+ New model config</SelectItem>
            </SelectContent>
          </Select>
        </Field>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Config name">
          <input className={input} required maxLength={60} placeholder="e.g. OpenAI mini" value={draft.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label="Provider">
          <Select
            value={draft.provider}
            onValueChange={(v) => {
              // Local model names are server-specific, so start blank and let "Load models" fill it.
              set({ provider: v as Draft["provider"], base_url: providers.find((p) => p.id === v)!.url, ...(v === "local" ? { model: "" } : {}) });
              setModels([]);
              setModelsMsg({});
            }}
          >
            <SelectTrigger className={trigger}><SelectValue /></SelectTrigger>
            <SelectContent position="popper">
              {providers.map((p) => <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Base URL">
          <input className={input} type="url" value={draft.base_url} onChange={(e) => set({ base_url: e.target.value })} placeholder="https://…/v1" />
        </Field>
        {draft.provider === "local" && (
          <div className="space-y-1.5 sm:col-span-2">
            <span className="block text-sm font-medium">Server</span>
            <div className="flex flex-wrap gap-2">
              {localServers.map((ls) => (
                <button
                  key={ls.label}
                  type="button"
                  aria-pressed={draft.base_url === ls.url}
                  onClick={() => {
                    set({ base_url: ls.url });
                    setModels([]);
                    setModelsMsg({});
                  }}
                  className={`rounded-md border px-3 py-1.5 text-sm ${draft.base_url === ls.url ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900" : "border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"}`}
                >
                  {ls.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-zinc-500">
              Sets the default port; edit the Base URL for another host or port. If this app runs in Docker, use <code>host.docker.internal</code> instead of <code>localhost</code>.
            </p>
          </div>
        )}
        <div className="space-y-1.5">
          <Field label="Model id">
            <span className="flex gap-2">
              <input className={input} list="model-options" value={draft.model} placeholder={draft.provider === "local" ? "Load models to pick one" : undefined} onChange={(e) => set({ model: e.target.value })} />
              <button type="button" onClick={loadModels} disabled={!draft.base_url} className={`${secondary} shrink-0 whitespace-nowrap`}>Load models</button>
            </span>
          </Field>
          <datalist id="model-options">{models.map((m) => <option key={m} value={m} />)}</datalist>
          {modelsMsg.error && <p role="alert" className="text-xs text-red-600 [overflow-wrap:anywhere]">{modelsMsg.error}</p>}
          {modelsMsg.ok && <p className="text-xs text-zinc-500">{modelsMsg.ok}</p>}
        </div>
        <Field label="API key">
          <input
            type="password"
            autoComplete="off"
            className={input}
            value={draft.api_key}
            placeholder={keyPlaceholder}
            onChange={(e) => set({ api_key: e.target.value })}
          />
        </Field>
      </div>
      {draft.has_api_key && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4" checked={draft.remove_key} onChange={(e) => set({ remove_key: e.target.checked, api_key: "" })} />
          Remove the saved API key
        </label>
      )}

      <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
        <summary className="cursor-pointer text-sm font-medium">Advanced settings</summary>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Field label="Temperature (0–2)">
            <input className={input} type="number" min={0} max={2} step={0.1} placeholder="default" value={draft.temperature} onChange={(e) => set({ temperature: e.target.value })} />
          </Field>
          <Field label="Top p (0–1)">
            <input className={input} type="number" min={0} max={1} step={0.05} placeholder="default" value={draft.top_p} onChange={(e) => set({ top_p: e.target.value })} />
          </Field>
          <Field label="Max output tokens">
            <input className={input} type="number" min={1} step={1} placeholder="default" value={draft.max_tokens} onChange={(e) => set({ max_tokens: e.target.value })} />
          </Field>
          <Field label="Seed">
            <input className={input} type="number" step={1} placeholder="random" value={draft.seed} onChange={(e) => set({ seed: e.target.value })} />
          </Field>
          <Field label="Request timeout (s)">
            <input className={input} type="number" min={1} max={600} placeholder="default" value={draft.request_timeout} onChange={(e) => set({ request_timeout: e.target.value })} />
          </Field>
          <Field label="Max retries (0–10)">
            <input className={input} type="number" min={0} max={10} step={1} required value={draft.max_retries} onChange={(e) => set({ max_retries: e.target.value })} />
          </Field>
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4" checked={draft.verify_ssl} onChange={(e) => set({ verify_ssl: e.target.checked })} />
          Verify TLS certificates (turn off only for a local endpoint with a self-signed certificate)
        </label>
      </details>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={primary} disabled={busy} onClick={save}>{draft.id ? "Save changes" : "Save model config"}</button>
        {draft.id && (
          <button type="button" className={secondary} disabled={busy} onClick={() => (confirmDelete ? remove() : setConfirmDelete(true))}>
            {confirmDelete ? "Click again to delete" : "Delete"}
          </button>
        )}
        {msg.error && <p role="alert" className="text-sm text-red-600">{msg.error}</p>}
        {msg.ok && <p role="status" className="text-sm text-green-600">{msg.ok}</p>}
      </div>

      <div className="flex items-center justify-between gap-4 rounded-lg border border-dashed border-zinc-300 p-4 text-sm dark:border-zinc-700">
        <div className="min-w-0 space-y-0.5">
          <p className="font-medium">Connection</p>
          {testing ? (
            <p className="text-zinc-500">Testing…</p>
          ) : draft.tested_at ? (
            <>
              <p className={`[overflow-wrap:anywhere] ${draft.test_ok ? "text-green-600" : "text-red-600"}`}>
                {draft.test_ok ? "✓ Connected" : "✗ Failed"} · {draft.test_latency_ms} ms · {draft.test_message}
              </p>
              <p className="text-xs text-zinc-500">Tested {new Date(`${draft.tested_at.replace(" ", "T")}Z`).toLocaleString()}</p>
            </>
          ) : (
            <p className="text-zinc-500">Sends one short message to check the URL, API key and model. Not tested yet.</p>
          )}
        </div>
        <button type="button" disabled={busy || testing} onClick={test} className={`${secondary} shrink-0 whitespace-nowrap`}>
          {draft.id ? "Test connection" : "Save & test"}
        </button>
      </div>

      <div className="flex items-center justify-between gap-4 rounded-lg border border-dashed border-zinc-300 p-4 text-sm dark:border-zinc-700">
        <div className="min-w-0 space-y-0.5">
          <p className="font-medium">Tool use · agent mode <span className="font-mono text-xs">{agentMode}</span></p>
          {probe.busy ? (
            <p className="text-zinc-500">Checking…</p>
          ) : probe.message ? (
            <p className={`[overflow-wrap:anywhere] ${probe.ok ? "text-green-600" : "text-red-600"}`}>{probe.ok ? "✓ " : "✗ "}{probe.message}</p>
          ) : (
            <p className="text-zinc-500">One real request asks the model to call a tool. If it can, the agent uses native tool calling; if not, it falls back to ReAct.</p>
          )}
        </div>
        <button type="button" disabled={busy || !!probe.busy} onClick={checkTools} className={`${secondary} shrink-0 whitespace-nowrap`}>
          Check tool use
        </button>
      </div>
    </>
  );
}

type Approval = { id: string; tool_id: string; risk_tier: number; arguments: Record<string, unknown>; status: string };
type ToolCallView = { name: string; arguments: unknown; result: unknown; status: string };
type Run = {
  run_id: string;
  status: "running" | "waiting_for_approval" | "succeeded" | "failed";
  approvals: Approval[];
  text: string | null;
  error: string | null;
  warnings: string[];
  trace: { model: string; tools_used: string[]; tokens: { total: number | null }; steps: { id: string; source: string; text: string | null; tool_calls: ToolCallView[] }[] } | null;
};

// Step 7: run the agent through the SDK (mock tools by default) and show what it did. A live run stops at every
// tier-2 call and shows the exact payload here until you approve or decline it.
function TestStep({ request }: { request: { spec: object; config_id: number | null; agent_mode: AgentMode } }) {
  const [prompt, setPrompt] = useState("");
  const [live, setLive] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const running = run?.status === "running" || run?.status === "waiting_for_approval";

  useEffect(() => {
    if (!run || !running) return;
    const t = setTimeout(async () => {
      const r = await api<Run>(`/api/sdk/runs/${run.run_id}`);
      if (r.ok) setRun(r.data);
      else setError(r.error);
    }, 1000);
    return () => clearTimeout(t);
  }, [run, running]);

  async function start() {
    setError("");
    setRun(null);
    const r = await api<{ run_id: string }>("/api/sdk/runs", json("POST", { ...request, prompt, mock: !live }));
    if (!r.ok) return setError(r.error);
    setRun({ run_id: r.data.run_id, status: "running", approvals: [], text: null, error: null, warnings: [], trace: null });
  }

  async function answer(a: Approval, approved: boolean) {
    const r = await api(`/api/sdk/runs/${run!.run_id}/approvals/${a.id}`, json("POST", { approved }));
    if (!r.ok) setError(r.error);
  }

  return (
    <>
      <Heading title="Test" sub="Mock mode (the default): tools return canned answers and never touch your live accounts. Every model call and tool call shows in the trace." />
      <div className="flex gap-2">
        <input className={input} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="e.g. Do I have unread mail?" onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), prompt.trim() && !running && start())} />
        <button type="button" className={primary} disabled={!prompt.trim() || running || !request.config_id} onClick={start}>{running ? "Running…" : "Run"}</button>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="size-4" checked={live} onChange={(e) => setLive(e.target.checked)} />
        Live run: tools act on your real accounts; every tier-2 action waits for your approval here
      </label>
      {!request.config_id && <p className="text-sm text-zinc-500">Save a model config in step 1 first.</p>}
      {error && <p role="alert" className="text-sm text-red-600 [overflow-wrap:anywhere]">{error}</p>}

      {run?.approvals.map((a) => (
        <div key={a.id} className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950/40">
          <p className="font-medium">
            {a.status === "pending" ? "Approval needed: " : `${a.status[0].toUpperCase()}${a.status.slice(1)}: `}
            <span className="font-mono">{a.tool_id}</span> (tier {a.risk_tier}) {a.status === "pending" ? "wants to run with" : "asked to run with"}
          </p>
          <pre className="overflow-auto rounded bg-white p-2 font-mono text-xs dark:bg-zinc-900">{JSON.stringify(a.arguments, null, 2)}</pre>
          {a.status === "pending" && (
            <div className="flex gap-2">
              <button type="button" className={primary} onClick={() => answer(a, true)}>Approve</button>
              <button type="button" className={secondary} onClick={() => answer(a, false)}>Decline</button>
            </div>
          )}
        </div>
      ))}

      {run && !running && (
        <div className="space-y-3">
          {run.text && <p className="whitespace-pre-wrap rounded-lg border border-zinc-200 p-3 text-sm dark:border-zinc-800">{run.text}</p>}
          {run.error && <p role="alert" className="text-sm text-red-600 [overflow-wrap:anywhere]">{run.error}</p>}
          {run.warnings.length > 0 && (
            <ul className="space-y-1 text-xs text-amber-700 dark:text-amber-300">{run.warnings.map((w) => <li key={w}>⚠ {w}</li>)}</ul>
          )}
          {run.trace && (
            <details open className="rounded-lg border border-zinc-200 p-3 text-sm dark:border-zinc-800">
              <summary className="cursor-pointer font-medium">
                Trace · {run.trace.model} · tools used: {run.trace.tools_used.join(", ") || "none"} · {run.trace.tokens.total ?? "?"} tokens
              </summary>
              <ol className="mt-3 space-y-3">
                {/* "user" steps are NAT's raw input records; the prompt is already in the box above. */}
                {run.trace.steps.filter((st) => st.source !== "user").map((st) => (
                  <li key={st.id} className="space-y-1">
                    <p className="text-xs uppercase text-zinc-500">{st.source}</p>
                    {st.text && <p className="whitespace-pre-wrap">{st.text}</p>}
                    {st.tool_calls.map((c, i) => (
                      <div key={i} className="rounded bg-zinc-50 p-2 font-mono text-xs dark:bg-zinc-950">
                        <p>→ {c.name}({JSON.stringify(c.arguments)}) · {c.status}</p>
                        <p className="whitespace-pre-wrap text-zinc-500">{typeof c.result === "string" ? c.result : JSON.stringify(c.result)}</p>
                      </div>
                    ))}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </>
  );
}
