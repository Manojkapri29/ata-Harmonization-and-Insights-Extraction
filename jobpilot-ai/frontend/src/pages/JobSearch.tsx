import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Bookmark, ExternalLink, FileUp, Link2, Play, Plus, Save, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useAsync, useTask } from "../lib/hooks";
import type { AssistedLink, SearchProfile, Source, Task } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, ChipsInput, ErrorBox, Field, Notice, PageHeader, Skeleton, Tabs, TaskProgress } from "../components/ui";

type Draft = Omit<SearchProfile, "id" | "last_run_at">;
const BLANK: Draft = { name: "New search", keywords: [], locations: [], experience_min: null, experience_max: null, include_remote: true,
  min_salary_monthly: null, posted_within_days: 7, sources: [], enabled: true, auto_run: false, interval_hours: 12 };

function bookmarklet(origin: string) {
  const code = `(()=>{const j=[...document.querySelectorAll('script[type="application/ld+json"]')].map(e=>e.textContent);` +
    `const t=(getSelection().toString()||document.body.innerText||'').slice(0,20000);` +
    `window.open('${origin}/import#'+encodeURIComponent(JSON.stringify({url:location.href,title:document.title,text:t,jsonld:j})),'_blank');})()`;
  return `javascript:${code}`;
}

/** React 19 refuses javascript: hrefs in JSX, so the bookmarklet URL is set on the DOM node directly. */
function BookmarkletLink({ code, onClick }: { code: string; onClick: () => void }) {
  const ref = useRef<HTMLAnchorElement>(null);
  useEffect(() => { ref.current?.setAttribute("href", code); }, [code]);
  return (
    <a ref={ref} onClick={(e) => { e.preventDefault(); onClick(); }} draggable
      className="ml-1 inline-flex cursor-grab items-center gap-1 rounded-md bg-brand-600 px-2 py-1 text-xs font-medium text-white">+ Save to JobPilot</a>
  );
}

export default function JobSearch() {
  const toast = useToast();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const profiles = useAsync(() => api.searchProfiles());
  const sources = useAsync(() => api.sources());
  const [selected, setSelected] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(BLANK);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<Task["result"]>(null);
  const [tab, setTab] = useState<"search" | "import">("search");
  const autoRan = useRef(false);

  const { task, track, running } = useTask((t) => {
    if (t.status === "completed") {
      setResult(t.result);
      const r = t.result!;
      toast.success(`Search finished: ${r.new_jobs} new job${r.new_jobs === 1 ? "" : "s"}${r.high_matches ? `, ${r.high_matches} high match` : ""}.`);
      profiles.reload(true);
    } else toast.error(`Search failed: ${t.message}`);
  });

  useEffect(() => {
    if (profiles.data && selected === null) setSelected(profiles.data[0]?.id ?? "new");
  }, [profiles.data, selected]);

  useEffect(() => {
    if (selected === "new") setDraft({ ...BLANK, sources: (sources.data ?? []).filter((s) => s.enabled).map((s) => s.key) });
    else if (selected != null) {
      const p = profiles.data?.find((x) => x.id === selected);
      if (p) { const { id: _id, last_run_at: _l, ...rest } = p; setDraft(rest); }
    }
  }, [selected, profiles.data, sources.data]);

  // "Find Jobs" from anywhere lands here with ?run=1
  useEffect(() => {
    if (params.get("run") && !autoRan.current && typeof selected === "number") {
      autoRan.current = true;
      params.delete("run");
      setParams(params, { replace: true });
      run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const save = async (): Promise<number | null> => {
    setSaving(true);
    try {
      const saved = selected === "new" || selected == null ? await api.createSearchProfile(draft) : await api.updateSearchProfile(selected, draft);
      await profiles.reload(true);
      setSelected(saved.id);
      toast.success("Search profile saved");
      return saved.id;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setSaving(false);
    }
  };

  const run = async () => {
    setResult(null);
    const id = typeof selected === "number" ? selected : await save();
    if (!id) return;
    try {
      if (selected !== "new") await api.updateSearchProfile(id, draft);
      track(await api.runSearchProfile(id));
    } catch (e) { toast.error((e as Error).message); }
  };

  const remove = async () => {
    if (typeof selected !== "number" || !confirm("Delete this search profile?")) return;
    await api.deleteSearchProfile(selected);
    setSelected(null);
    profiles.reload();
  };

  const linksByBoard = useMemo(() => {
    const m: Record<string, AssistedLink[]> = {};
    (result?.assisted_links ?? []).forEach((l: AssistedLink) => { (m[l.board || l.source] ||= []).push(l); });
    return m;
  }, [result]);

  if (profiles.error) return <ErrorBox message={profiles.error} onRetry={() => profiles.reload()} />;
  const srcList = sources.data ?? [];
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div className="space-y-6">
      <PageHeader title="Job Search" subtitle="Search configured sources in the background, or import jobs you found yourself." />
      <Tabs tabs={[{ id: "search", label: "Search profiles" }, { id: "import", label: "Import a job" }]} value={tab} onChange={setTab} />

      {tab === "search" && (profiles.loading || sources.loading ? <Skeleton /> : (
        <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
          <Card title="Profiles" bodyClass="p-2">
            <ul className="space-y-1">
              {profiles.data!.map((p) => (
                <li key={p.id}>
                  <button onClick={() => setSelected(p.id)} className={`w-full rounded-lg px-3 py-2 text-left text-sm ${selected === p.id ? "bg-brand-50 text-brand-700 dark:bg-brand-600/15 dark:text-brand-100" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
                    <div className="font-medium">{p.name}</div>
                    <div className="text-xs text-slate-500">{p.auto_run ? `Auto every ${p.interval_hours}h` : "Manual"}{p.last_run_at ? ` · ran ${new Date(p.last_run_at + "Z").toLocaleString("en-IN", { dateStyle: "short", timeStyle: "short" })}` : ""}</div>
                  </button>
                </li>
              ))}
            </ul>
            <Button variant="ghost" className="mt-2 w-full" icon={<Plus className="h-4 w-4" />} onClick={() => setSelected("new")}>New profile</Button>
          </Card>

          <div className="space-y-6">
            <Card title={selected === "new" ? "New search profile" : "Edit search profile"}
              action={<div className="flex gap-2">
                {typeof selected === "number" && <Button variant="ghost" icon={<Trash2 className="h-4 w-4" />} onClick={remove} aria-label="Delete profile" />}
                <Button icon={<Save className="h-4 w-4" />} loading={saving} onClick={save}>Save</Button>
                <Button variant="primary" icon={<Play className="h-4 w-4" />} loading={running} onClick={run}>Find Jobs</Button>
              </div>}>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Profile name"><input className="input" value={draft.name} onChange={(e) => set("name", e.target.value)} /></Field>
                <Field label="Posted within">
                  <select className="input" value={draft.posted_within_days} onChange={(e) => set("posted_within_days", Number(e.target.value))}>
                    <option value={1}>24 hours</option><option value={3}>3 days</option><option value={7}>7 days</option><option value={30}>30 days</option>
                  </select>
                </Field>
                <Field label="Keywords" hint="Press Enter after each role">
                  <ChipsInput value={draft.keywords} onChange={(v) => set("keywords", v)} placeholder="Data Analyst, MIS Executive…" />
                </Field>
                <Field label="Locations" hint="Delhi NCR covers Noida, Gurugram, Ghaziabad, Faridabad">
                  <ChipsInput value={draft.locations} onChange={(v) => set("locations", v)} placeholder="Delhi NCR, Noida…" />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Experience from (yrs)"><input type="number" min={0} className="input" value={draft.experience_min ?? ""} onChange={(e) => set("experience_min", e.target.value === "" ? null : Number(e.target.value))} /></Field>
                  <Field label="to (yrs)"><input type="number" min={0} className="input" value={draft.experience_max ?? ""} onChange={(e) => set("experience_max", e.target.value === "" ? null : Number(e.target.value))} /></Field>
                </div>
                <Field label="Minimum salary (₹ / month)" hint="Jobs that state a lower maximum are skipped">
                  <input type="number" min={0} step={1000} className="input" value={draft.min_salary_monthly ?? ""} onChange={(e) => set("min_salary_monthly", e.target.value === "" ? null : Number(e.target.value))} />
                </Field>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.include_remote} onChange={(e) => set("include_remote", e.target.checked)} /> Include remote jobs</label>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <label className="flex items-center gap-2 whitespace-nowrap"><input type="checkbox" checked={draft.auto_run} onChange={(e) => set("auto_run", e.target.checked)} /> Run automatically every</label>
                  <input type="number" min={1} max={168} className="input w-20" value={draft.interval_hours} onChange={(e) => set("interval_hours", Number(e.target.value))} /> hours
                </div>
              </div>
              <div className="mt-5">
                <span className="label">Sources</span>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {srcList.map((s: Source) => (
                    <label key={s.key} className="flex items-start gap-2 rounded-lg border border-slate-200 p-2.5 text-sm dark:border-slate-800">
                      <input type="checkbox" className="mt-0.5" checked={draft.sources.includes(s.key)}
                        onChange={(e) => set("sources", e.target.checked ? [...draft.sources, s.key] : draft.sources.filter((x) => x !== s.key))} />
                      <span>
                        <span className="font-medium">{s.name}</span>{" "}
                        {s.kind === "assisted" && <Badge tone="violet">Browser-assisted</Badge>}
                        {s.kind === "demo" && <Badge tone="amber">Sample data</Badge>}
                        {s.missing_credentials.length > 0 && <Badge tone="red">Needs API key</Badge>}
                        {s.kind === "company" && !s.config?.companies && <Badge>Add companies in Settings</Badge>}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            </Card>

            <TaskProgress task={task} />

            {result && (
              <Card title="Search results" action={<Button variant="primary" onClick={() => nav("/matches?sort=match_score")}>View matches</Button>}>
                <p className="mb-3 text-sm"><b>{result.new_jobs}</b> new jobs, <b>{result.high_matches}</b> high matches.</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-xs text-slate-500"><th className="py-1">Source</th><th>Status</th><th>Found</th><th>Kept</th><th>New</th><th>Note</th></tr></thead>
                    <tbody>
                      {Object.entries(result.sources as Record<string, any>).map(([k, v]) => (
                        <tr key={k} className="border-t border-slate-100 dark:border-slate-800">
                          <td className="py-1.5 font-medium">{srcList.find((s) => s.key === k)?.name ?? k}</td>
                          <td><Badge tone={v.status === "ok" ? "green" : v.status === "assisted" ? "violet" : "red"}>{v.status}</Badge></td>
                          <td>{v.found}</td><td>{v.kept}</td><td>{v.new}</td>
                          <td className="max-w-xs truncate text-xs text-slate-500" title={v.message}>{v.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {Object.keys(linksByBoard).length > 0 && (
                  <div className="mt-5">
                    <h3 className="mb-1 text-sm font-semibold">Open these searches in your browser</h3>
                    <p className="mb-3 text-xs text-slate-500">These boards don't allow automated access. Open a link, and when a job looks good, import it with the bookmarklet (Import tab).</p>
                    <div className="grid gap-3 md:grid-cols-2">
                      {Object.entries(linksByBoard).map(([board, links]) => (
                        <div key={board} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                          <div className="mb-1.5 text-sm font-medium">{board}</div>
                          <div className="flex flex-wrap gap-1.5">
                            {links.map((l) => (
                              <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1 text-xs hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700">
                                {l.label} <ExternalLink className="h-3 w-3" />
                              </a>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            )}
          </div>
        </div>
      ))}

      {tab === "import" && <ImportPanel />}
    </div>
  );
}

function ImportPanel() {
  const toast = useToast();
  const nav = useNavigate();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({ title: "", company: "", location: "", job_url: "", salary_text: "", experience_text: "", description: "" });
  const origin = window.location.origin;

  const done = (jobs: { id: number; title: string }[]) => {
    toast.success(`Imported ${jobs.length} job${jobs.length === 1 ? "" : "s"}`);
    if (jobs.length === 1) nav(`/jobs/${jobs[0].id}`);
    else nav("/matches?sort=created_at");
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title={<span className="flex items-center gap-2"><Bookmark className="h-4 w-4" /> Browser bookmarklet (LinkedIn, Naukri, Indeed…)</span>}>
        <ol className="list-decimal space-y-1.5 pl-5 text-sm text-slate-600 dark:text-slate-300">
          <li>Drag this button to your bookmarks bar: <BookmarkletLink code={bookmarklet(origin)} onClick={() => toast.info("Drag it to your bookmarks bar, then click it on a job page.")} /></li>
          <li>Open any job page you're viewing (you stay logged in as yourself).</li>
          <li>Click the bookmark. JobPilot opens and imports the job; select text first to import only the selection.</li>
        </ol>
        <Notice>The bookmarklet only reads the page you are already looking at. JobPilot never logs in, stores passwords, or crawls these sites.</Notice>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Link2 className="h-4 w-4" /> Import by URL</span>}>
        <p className="mb-3 text-sm text-slate-500">Works for public job pages and company career pages (reads schema.org JobPosting data, respects robots.txt). Login-only pages need the bookmarklet.</p>
        <form className="flex gap-2" onSubmit={async (e) => {
          e.preventDefault();
          setBusy("url");
          try { done(await api.importUrl(url)); } catch (err) { toast.error((err as Error).message); } finally { setBusy(""); }
        }}>
          <input className="input" type="url" required placeholder="https://company.com/careers/data-analyst" value={url} onChange={(e) => setUrl(e.target.value)} />
          <Button variant="primary" loading={busy === "url"} type="submit">Import</Button>
        </form>
      </Card>

      <Card title="Paste a job description" className="lg:col-span-2">
        <form className="grid gap-3 md:grid-cols-3" onSubmit={async (e) => {
          e.preventDefault();
          setBusy("manual");
          try { done([await api.createJob(form)]); } catch (err) { toast.error((err as Error).message); } finally { setBusy(""); }
        }}>
          <Field label="Job title *"><input className="input" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="Company"><input className="input" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></Field>
          <Field label="Location"><input className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
          <Field label="Job URL"><input className="input" value={form.job_url} onChange={(e) => setForm({ ...form, job_url: e.target.value })} /></Field>
          <Field label="Salary (as written)"><input className="input" placeholder="₹5-7 LPA" value={form.salary_text} onChange={(e) => setForm({ ...form, salary_text: e.target.value })} /></Field>
          <Field label="Experience (as written)"><input className="input" placeholder="3-5 years" value={form.experience_text} onChange={(e) => setForm({ ...form, experience_text: e.target.value })} /></Field>
          <div className="md:col-span-3"><Field label="Job description"><textarea className="input min-h-[160px]" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field></div>
          <div className="md:col-span-3"><Button variant="primary" type="submit" loading={busy === "manual"}>Save & analyze</Button></div>
        </form>
      </Card>

      <Card title={<span className="flex items-center gap-2"><FileUp className="h-4 w-4" /> Import a file (CSV, Excel, JSON)</span>} className="lg:col-span-2">
        <p className="mb-3 text-sm text-slate-500">Columns: <code>title</code> (required), company, location, description, job_url, salary_text, experience_text. You can re-import a JobPilot export.</p>
        <input type="file" accept=".csv,.xlsx,.json" onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          try {
            const r = await api.importJobs(f);
            toast.success(`Imported ${r.imported}, updated ${r.updated}, skipped ${r.skipped}`);
          } catch (err) { toast.error((err as Error).message); }
          e.target.value = "";
        }} />
        <p className="mt-3 text-xs text-slate-500">Exports live in <Link to="/settings" className="underline">Settings → Import / Export</Link>.</p>
      </Card>
    </div>
  );
}
