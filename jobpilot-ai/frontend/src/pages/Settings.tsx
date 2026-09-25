import { useEffect, useState } from "react";
import { Download, FlaskConical, Plus, Save, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import type { Profile, Source } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, ChipsInput, ErrorBox, Field, Notice, PageHeader, Skeleton, Tabs } from "../components/ui";

export default function SettingsPage() {
  const [tab, setTab] = useState<"profile" | "ai" | "sources" | "followups" | "data">("profile");
  return (
    <div className="space-y-5">
      <PageHeader title="Settings" />
      <Tabs tabs={[{ id: "profile", label: "Profile" }, { id: "ai", label: "AI provider" }, { id: "sources", label: "Job sources" },
        { id: "followups", label: "Follow-ups & alerts" }, { id: "data", label: "Import / Export" }]} value={tab} onChange={setTab} />
      {tab === "profile" && <ProfileForm />}
      {tab === "ai" && <AiSettings />}
      {tab === "sources" && <Sources />}
      {tab === "followups" && <FollowupSettings />}
      {tab === "data" && <DataSettings />}
    </div>
  );
}

function ProfileForm() {
  const toast = useToast();
  const p = useAsync(() => api.profile());
  const [f, setF] = useState<Profile | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (p.data) setF(p.data); }, [p.data]);
  if (p.error) return <ErrorBox message={p.error} />;
  if (!f) return <Skeleton />;
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setF({ ...f, [k]: v });
  const num = (v: string) => (v === "" ? null : Number(v));
  return (
    <Card title="Your profile" action={<Button variant="primary" icon={<Save className="h-4 w-4" />} loading={saving} onClick={async () => {
      setSaving(true);
      try { const { id: _id, ...body } = f; await api.saveProfile(body); toast.success("Profile saved; all jobs re-scored"); } catch (e) { toast.error((e as Error).message); } finally { setSaving(false); }
    }}>Save</Button>}>
      <Notice>Used for matching and messages together with your resume. Only enter what's true: generated resumes and messages draw on these facts.</Notice>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Field label="Full name"><input className="input" value={f.full_name} onChange={(e) => set("full_name", e.target.value)} /></Field>
        <Field label="Headline"><input className="input" value={f.headline} onChange={(e) => set("headline", e.target.value)} /></Field>
        <Field label="Email (used in message signatures)"><input className="input" type="email" value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Phone"><input className="input" value={f.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
        <Field label="Current city" hint="Used for lines like “I'm based in …”. Leave blank if you'd rather not say."><input className="input" value={f.location} onChange={(e) => set("location", e.target.value)} /></Field>
        <Field label="LinkedIn URL"><input className="input" value={f.linkedin_url} onChange={(e) => set("linkedin_url", e.target.value)} /></Field>
        <Field label="Total experience (years)"><input type="number" step="0.5" min={0} className="input" value={f.total_experience_years ?? ""} onChange={(e) => set("total_experience_years", num(e.target.value))} /></Field>
        <Field label="Notice period"><input className="input" value={f.notice_period} onChange={(e) => set("notice_period", e.target.value)} /></Field>
        <Field label="Current salary (₹ / month)"><input type="number" className="input" value={f.current_salary_monthly ?? ""} onChange={(e) => set("current_salary_monthly", num(e.target.value))} /></Field>
        <Field label="Expected salary (₹ / month)" hint="Blank = current + ~15% for salary matching"><input type="number" className="input" value={f.expected_salary_monthly ?? ""} onChange={(e) => set("expected_salary_monthly", num(e.target.value))} /></Field>
        <Field label="Target roles"><ChipsInput value={f.target_roles} onChange={(v) => set("target_roles", v)} /></Field>
        <Field label="Preferred locations"><ChipsInput value={f.preferred_locations} onChange={(v) => set("preferred_locations", v)} /></Field>
        <Field label="Skills"><ChipsInput value={f.skills} onChange={(v) => set("skills", v)} /></Field>
        <Field label="Education"><ChipsInput value={f.education} onChange={(v) => set("education", v)} /></Field>
        <div className="md:col-span-2"><Field label="Summary"><textarea className="input min-h-[90px]" value={f.summary} onChange={(e) => set("summary", e.target.value)} /></Field></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.open_to_remote} onChange={(e) => set("open_to_remote", e.target.checked)} /> Open to remote</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.open_to_relocation_if_relevant} onChange={(e) => set("open_to_relocation_if_relevant", e.target.checked)} /> Open to other locations if the job is highly relevant</label>
      </div>
    </Card>
  );
}

function AiSettings() {
  const toast = useToast();
  const s = useAsync(() => api.settings());
  const [ai, setAi] = useState<{ provider?: string; model?: string; base_url?: string }>({});
  const [test, setTest] = useState<{ ok: boolean; message: string } | null>(null);
  const [busy, setBusy] = useState("");
  useEffect(() => { if (s.data) setAi(s.data.ai ?? {}); }, [s.data]);
  if (!s.data) return <Skeleton />;
  const env = s.data.ai_env;
  const status = s.data.ai_status;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="AI provider" action={<Badge tone={status.available ? "green" : "slate"}>{status.available ? `Active: ${status.provider}${status.model ? ` · ${status.model}` : ""}` : "Rules only (no AI)"}</Badge>}>
        <p className="mb-3 text-sm text-slate-500">Everything works without AI. With AI on, it rephrases summaries, bullets and messages, and every output is checked so it can't add skills, numbers or employers you don't have.</p>
        <div className="grid gap-3">
          <Field label="Provider">
            <select className="input" value={ai.provider ?? ""} onChange={(e) => setAi({ ...ai, provider: e.target.value })}>
              <option value="">Use .env setting ({env.provider})</option><option value="none">None (rules only)</option>
              <option value="ollama">Ollama (local, free)</option><option value="openai">OpenAI-compatible API</option><option value="anthropic">Anthropic (Claude)</option>
            </select>
          </Field>
          <Field label="Model (optional override)"><input className="input" placeholder={ai.provider === "anthropic" ? env.anthropic_model : ai.provider === "ollama" ? env.ollama_model : env.openai_model || "model name"} value={ai.model ?? ""} onChange={(e) => setAi({ ...ai, model: e.target.value })} /></Field>
          {(ai.provider === "openai" || ai.provider === "ollama") && <Field label="Base URL (optional override)"><input className="input" placeholder={ai.provider === "ollama" ? env.ollama_base_url : "https://api.openai.com/v1"} value={ai.base_url ?? ""} onChange={(e) => setAi({ ...ai, base_url: e.target.value })} /></Field>}
          <div className="flex gap-2">
            <Button variant="primary" loading={busy === "save"} onClick={async () => { setBusy("save"); try { await api.saveSettings({ ai }); await s.reload(true); toast.success("AI settings saved"); } finally { setBusy(""); } }}>Save</Button>
            <Button icon={<FlaskConical className="h-4 w-4" />} loading={busy === "test"} onClick={async () => { setBusy("test"); try { setTest(await api.testAi()); } finally { setBusy(""); } }}>Test connection</Button>
          </div>
          {test && <Notice tone={test.ok ? "info" : "warn"}>{test.ok ? "✓ Connected: " : "✗ "}{test.message}</Notice>}
        </div>
      </Card>
      <Card title="API keys live in backend/.env">
        <Notice tone="warn">For security, keys are never entered or stored through this page. Edit <code>backend/.env</code> and restart the backend.</Notice>
        <ul className="mt-3 space-y-1 text-sm">
          <li>OpenAI-compatible key: <Badge tone={env.openai_key_set ? "green" : "slate"}>{env.openai_key_set ? "set" : "not set"}</Badge></li>
          <li>Anthropic key: <Badge tone={env.anthropic_key_set ? "green" : "slate"}>{env.anthropic_key_set ? "set" : "not set"}</Badge></li>
          <li>Ollama URL: <code>{env.ollama_base_url}</code> (no key needed)</li>
        </ul>
        <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{`# backend/.env
AI_PROVIDER=ollama          # or openai / anthropic / none
OLLAMA_MODEL=llama3.1
# OPENAI_API_KEY=...        OPENAI_MODEL=...
# ANTHROPIC_API_KEY=...     ANTHROPIC_MODEL=claude-opus-5`}</pre>
      </Card>
    </div>
  );
}

function Sources() {
  const toast = useToast();
  const src = useAsync(() => api.sources());
  const [cfg, setCfg] = useState<Record<string, Record<string, string>>>({});
  useEffect(() => { if (src.data) setCfg(Object.fromEntries(src.data.map((s) => [s.key, s.config ?? {}]))); }, [src.data]);
  if (!src.data) return <Skeleton />;
  const kinds: [Source["kind"], string][] = [["api", "Official / public APIs"], ["company", "Company career pages"], ["feed", "Feeds"], ["assisted", "Browser-assisted (no scraping)"], ["demo", "Testing"]];
  return (
    <div className="space-y-6">
      {kinds.map(([kind, title]) => (
        <Card key={kind} title={title}>
          <div className="grid gap-3 md:grid-cols-2">
            {src.data!.filter((s) => s.kind === kind).map((s) => (
              <div key={s.key} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium">{s.name}</div>
                    <div className="text-xs text-slate-500">{s.description}</div>
                  </div>
                  <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={s.enabled} onChange={async (e) => { await api.updateSource(s.key, { enabled: e.target.checked }); src.reload(true); }} /> Enabled</label>
                </div>
                {s.requires_credentials.length > 0 && <div className="mt-2 text-xs">Needs <code>{s.requires_credentials.join(", ")}</code> in backend/.env: <Badge tone={s.missing_credentials.length ? "red" : "green"}>{s.missing_credentials.length ? "missing" : "configured"}</Badge></div>}
                {s.terms_note && <p className="mt-1 text-xs text-slate-500">{s.terms_note}</p>}
                {s.config_fields.map((fld) => (
                  <div key={fld.name} className="mt-2 flex gap-2">
                    <input className="input" aria-label={fld.label} placeholder={`${fld.label}: ${fld.placeholder}`} value={cfg[s.key]?.[fld.name] ?? ""}
                      onChange={(e) => setCfg({ ...cfg, [s.key]: { ...cfg[s.key], [fld.name]: e.target.value } })} />
                    <Button onClick={async () => { await api.updateSource(s.key, { config: cfg[s.key] }); toast.success(`${s.name} saved`); src.reload(true); }}>Save</Button>
                  </div>
                ))}
                {s.last_run_at && <p className="mt-2 text-xs text-slate-400">Last run: {new Date(s.last_run_at + "Z").toLocaleString("en-IN")} · {s.last_count} kept · {s.last_status}</p>}
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function FollowupSettings() {
  const toast = useToast();
  const s = useAsync(() => api.settings());
  const [steps, setSteps] = useState<{ day: number; channel: string; label: string }[]>([]);
  const [high, setHigh] = useState(75);
  const [rel, setRel] = useState(60);
  useEffect(() => { if (s.data) { setSteps(s.data.followup_schedule); setHigh(s.data.high_match_threshold); setRel(s.data.relevant_threshold); } }, [s.data]);
  if (!s.data) return <Skeleton />;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Follow-up schedule" action={<Button variant="primary" onClick={async () => { try { await api.saveSettings({ followup_schedule: steps }); toast.success("Schedule saved (applies to new applications)"); } catch (e) { toast.error((e as Error).message); } }}>Save</Button>}>
        <div className="space-y-2">
          {steps.map((st, i) => (
            <div key={i} className="grid grid-cols-[80px_1fr_1.5fr_auto] items-center gap-2">
              <input type="number" min={0} aria-label="Day" className="input" value={st.day} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, day: Number(e.target.value) } : x))} />
              <select className="input" aria-label="Channel" value={st.channel} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, channel: e.target.value } : x))}>
                {["application", "linkedin_whatsapp", "email", "email_final", "call"].map((c) => <option key={c}>{c}</option>)}
              </select>
              <input className="input" aria-label="Label" value={st.label} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, label: e.target.value } : x))} />
              <Button variant="ghost" aria-label="Remove step" icon={<Trash2 className="h-4 w-4" />} onClick={() => setSteps(steps.filter((_, j) => j !== i))} />
            </div>
          ))}
          <Button variant="ghost" icon={<Plus className="h-4 w-4" />} onClick={() => setSteps([...steps, { day: 21, channel: "email", label: "Extra follow-up" }])}>Add step</Button>
        </div>
      </Card>
      <Card title="Alerts & thresholds" action={<Button variant="primary" onClick={async () => { await api.saveSettings({ high_match_threshold: high, relevant_threshold: rel }); toast.success("Saved"); }}>Save</Button>}>
        <Field label={`"🔥 High match" alert at ${high}%+`}><input type="range" min={50} max={95} value={high} onChange={(e) => setHigh(Number(e.target.value))} className="w-full" /></Field>
        <Field label={`"Relevant" jobs at ${rel}%+`}><input type="range" min={30} max={90} value={rel} onChange={(e) => setRel(Number(e.target.value))} className="w-full" /></Field>
        <p className="mt-2 text-xs text-slate-500">New jobs at or above the high-match threshold create an alert in the bell menu. Background searches run for profiles with “Run automatically” on{s.data.scheduler_enabled ? "" : " (scheduler is disabled in .env)"}.</p>
      </Card>
    </div>
  );
}

function DataSettings() {
  const entities = [["jobs", "Jobs"], ["applications", "Applications"], ["contacts", "HR contacts"], ["communications", "Messages"], ["analytics", "Analytics"]];
  return (
    <Card title="Export">
      <div className="space-y-2">
        {entities.map(([k, l]) => (
          <div key={k} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <span className="font-medium">{l}</span>
            <div className="flex gap-2">{["csv", "xlsx", "json"].map((f) => <a key={f} href={api.exportUrl(k, f)}><Button icon={<Download className="h-4 w-4" />}>{f.toUpperCase()}</Button></a>)}</div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-sm text-slate-500">To import jobs from CSV / Excel / JSON, use Job Search → Import a job.</p>
    </Card>
  );
}
