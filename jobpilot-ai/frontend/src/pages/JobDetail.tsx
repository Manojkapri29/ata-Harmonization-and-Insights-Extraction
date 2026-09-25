import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft, Bookmark, CheckCircle2, Download, ExternalLink, FileText, Mail, MessageCircle, Rocket,
  Search, Send, Share2 as Linkedin, Sparkles, Trash2, UserPlus, Wand2,
} from "lucide-react";
import { api } from "../lib/api";
import { useAsync, useTask } from "../lib/hooks";
import { APP_STATUSES, CHANNEL_LABELS, type AtsResult, type Communication, type Contact, type JobDetail, type Match, type ResumeVersion } from "../lib/types";
import { useToast } from "../components/Toast";
import {
  Badge, Bar, Button, Card, CopyButton, Empty, ErrorBox, Field, Modal, Notice, ScoreBadge, ScoreRing, Skeleton, Tabs,
  TaskProgress, fmtDate, fmtExp, fmtSalary,
} from "../components/ui";

const KIT_STEPS = ["Analyze JD", "Calculate match", "Analyze current resume", "Generate tailored resume", "Generate cover letter",
  "Generate HR email", "Generate WhatsApp message", "Generate LinkedIn connection note", "Generate LinkedIn DM", "Save to application record"];

type TabId = "overview" | "ats" | "resume" | "cover_letter" | "email" | "whatsapp" | "linkedin_note" | "linkedin_dm" | "track";
const TAB_ALIASES: Record<string, TabId> = { linkedin: "linkedin_note", analyze: "overview" };

export default function JobDetailPage() {
  const id = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const job = useAsync(() => api.job(id), [id]);
  const comms = useAsync(() => api.jobComms(id), [id]);
  const versions = useAsync(() => api.jobVersions(id), [id]);
  const resumes = useAsync(() => api.resumes());
  const [busy, setBusy] = useState("");
  const [jd, setJd] = useState<any>(null);
  const [ats, setAts] = useState<AtsResult | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);

  const raw = params.get("tab") || "overview";
  const tab: TabId = (TAB_ALIASES[raw] ?? raw) as TabId;
  const setTab = (t: TabId) => { const n = new URLSearchParams(params); n.set("tab", t); setParams(n, { replace: true }); };

  const kitTask = useTask((t) => {
    if (t.status === "completed") {
      toast.success("Application kit ready: ATS analysis, tailored resume and 5 messages.");
      reloadAll();
      loadKitExtras();
      setTab("resume");
    } else toast.error(`Kit failed: ${t.message}`);
  });

  const reloadAll = () => { job.reload(true); comms.reload(true); versions.reload(true); };
  const loadKitExtras = async () => {
    try { const k = await api.getKit(id); if (k) { setJd(k.jd); setAts(k.resume_ats); } } catch { /* network error: page still works */ }
  };
  useEffect(() => { loadKitExtras(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [id]);

  const latest = useMemo(() => {
    const m: Record<string, Communication> = {};
    (comms.data ?? []).forEach((c) => { if (!m[c.channel]) m[c.channel] = c; });
    return m;
  }, [comms.data]);

  if (job.error) return <ErrorBox message={job.error} onRetry={() => job.reload()} />;
  if (job.loading || !job.data) return <Skeleton rows={8} />;
  const j = job.data;
  const m = j.match_details as Match;
  const hasResume = (resumes.data?.length ?? 0) > 0;

  const act = async (key: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(key);
    try { await fn(); if (ok) toast.success(ok); } catch (e) { toast.error((e as Error).message); } finally { setBusy(""); }
  };
  const analyze = () => act("analyze", async () => { setJd(await api.analyzeJob(id)); await api.matchJob(id); job.reload(true); setTab("overview"); }, "Job analyzed");
  const runAts = () => act("ats", async () => { setAts(await api.atsForJob(id)); setTab("ats"); });
  const tailor = () => act("tailor", async () => { await api.tailorForJob(id); versions.reload(true); job.reload(true); setTab("resume"); }, "Tailored resume created");
  const gen = (ch: string) => act(ch, async () => { await api.generateComms(id, [ch]); await comms.reload(true); setTab(ch as TabId); }, `${CHANNEL_LABELS[ch]} drafted`);
  const save = () => act("save", async () => { await api.updateJob(id, { status: "Shortlisted" }); job.reload(true); }, "Saved to your shortlist");
  const kit = () => act("kit", async () => kitTask.track(await api.kit(id)));
  const apply = () => act("apply", async () => {
    const r = await api.apply(id, { resume_version_id: versions.data?.[0]?.id ?? null });
    setConfirmApply(false);
    job.reload(true);
    toast.success(`Marked as applied. ${r.followups.length} follow-ups scheduled (next ${fmtDate(r.next_followup_date)}).`);
    setTab("track");
  });

  const TABS: { id: TabId; label: React.ReactNode }[] = [
    { id: "overview", label: "Overview" }, { id: "ats", label: "ATS" }, { id: "resume", label: <>Resume{versions.data?.length ? " ✓" : ""}</> },
    ...(["cover_letter", "email", "whatsapp", "linkedin_note", "linkedin_dm"] as TabId[]).map((c) => ({ id: c, label: <>{CHANNEL_LABELS[c]}{latest[c] ? " ✓" : ""}</> })),
    { id: "track", label: "Track" },
  ];

  return (
    <div className="space-y-5">
      <button onClick={() => nav(-1)} className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"><ArrowLeft className="h-4 w-4" /> Back</button>

      <div className="card p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{j.title}</h1>
              {j.source === "demo" && <Badge tone="amber">Sample job — not real</Badge>}
              {j.application_status && <Badge tone="violet">{j.application_status}</Badge>}
            </div>
            <div className="mt-1 text-sm text-slate-600 dark:text-slate-300">{j.company || "Company not stated"} · {j.location || "Location not stated"}{j.remote ? " · Remote" : ""}</div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <Badge>{fmtSalary(j)}</Badge><Badge>{fmtExp(j)}</Badge>
              {j.employment_type && <Badge>{j.employment_type}</Badge>}
              <Badge>Posted {fmtDate(j.posted_date || j.created_at)}</Badge>
              <Badge className="capitalize">{j.source}</Badge>
              {j.ats_score != null && <Badge tone="blue">ATS estimate {j.ats_score}%</Badge>}
            </div>
            <div className="mt-3 flex flex-wrap gap-3 text-sm">
              {j.job_url && <a className="inline-flex items-center gap-1 text-brand-600 hover:underline" href={j.job_url} target="_blank" rel="noreferrer">Open posting <ExternalLink className="h-3.5 w-3.5" /></a>}
              {j.application_url && j.application_url !== j.job_url && <a className="inline-flex items-center gap-1 text-brand-600 hover:underline" href={j.application_url} target="_blank" rel="noreferrer">Apply page <ExternalLink className="h-3.5 w-3.5" /></a>}
            </div>
          </div>
          {m && "overall" in m && <ScoreRing score={m.overall} label="Match" />}
        </div>

        <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
          <Button variant="primary" icon={<Rocket className="h-4 w-4" />} loading={busy === "kit" || kitTask.running} disabled={!hasResume} onClick={kit}
            title={hasResume ? "" : "Upload your master resume first"}>Generate Application Kit</Button>
          <Button icon={<Search className="h-4 w-4" />} loading={busy === "analyze"} onClick={analyze}>Analyze Job</Button>
          <Button icon={<Wand2 className="h-4 w-4" />} loading={busy === "tailor"} disabled={!hasResume} onClick={tailor}>Tailor Resume</Button>
          <Button icon={<FileText className="h-4 w-4" />} loading={busy === "cover_letter"} onClick={() => gen("cover_letter")}>Generate Cover Letter</Button>
          <Button icon={<Mail className="h-4 w-4" />} loading={busy === "email"} onClick={() => gen("email")}>Generate Email</Button>
          <Button icon={<MessageCircle className="h-4 w-4" />} loading={busy === "whatsapp"} onClick={() => gen("whatsapp")}>Generate WhatsApp</Button>
          <Button icon={<Linkedin className="h-4 w-4" />} loading={busy === "linkedin_note"} onClick={() => gen("linkedin_note")}>Generate LinkedIn Note</Button>
          <Button icon={<Bookmark className="h-4 w-4" />} loading={busy === "save"} onClick={save} disabled={!!j.application_status}>Save Job</Button>
          <Button variant="success" icon={<CheckCircle2 className="h-4 w-4" />} disabled={["Applied", "HR Contacted", "Interview", "Assessment", "Offer"].includes(j.application_status ?? "")}
            onClick={() => setConfirmApply(true)}>Mark Applied</Button>
        </div>
        {!hasResume && resumes.data && <div className="mt-3"><Notice tone="warn">Upload your master resume on the <Link className="underline" to="/resume">Resume page</Link> to tailor resumes and build application kits.</Notice></div>}
        {kitTask.task && <div className="mt-4"><TaskProgress task={kitTask.task} steps={KIT_STEPS} /></div>}
      </div>

      <Tabs tabs={TABS} value={tab} onChange={setTab} />

      {tab === "overview" && <Overview job={j} match={m} jd={jd} onAnalyze={analyze} />}
      {tab === "ats" && (ats ? <AtsView ats={ats} /> : (
        <Card><Empty title="No ATS analysis yet" text="Compare your master resume with this job description." action={<Button variant="primary" loading={busy === "ats"} disabled={!hasResume} onClick={runAts}>Run ATS analysis</Button>} /></Card>
      ))}
      {tab === "resume" && <ResumeVersions versions={versions.data ?? []} loading={versions.loading} onTailor={tailor} busy={busy === "tailor"} hasResume={hasResume} onDeleted={() => versions.reload(true)} />}
      {(["cover_letter", "email", "whatsapp", "linkedin_note", "linkedin_dm"] as TabId[]).includes(tab) && (
        latest[tab] ? <MessageEditor key={latest[tab].id} comm={latest[tab]} onSaved={() => comms.reload(true)} onRegenerate={() => gen(tab)} regenerating={busy === tab} />
          : <Card><Empty title={`No ${CHANNEL_LABELS[tab]} yet`} action={<Button variant="primary" loading={busy === tab} onClick={() => gen(tab)}>Generate {CHANNEL_LABELS[tab]}</Button>} /></Card>
      )}
      {tab === "track" && <TrackPanel job={j} onChange={() => { job.reload(true); comms.reload(true); }} />}

      <Modal open={confirmApply} onClose={() => setConfirmApply(false)} title="Mark as applied?">
        <p className="text-sm text-slate-600 dark:text-slate-300">Confirm that <b>you</b> submitted the application for <b>{j.title}</b> at <b>{j.company}</b>. JobPilot never applies for you.</p>
        <p className="mt-2 text-sm text-slate-500">Follow-up reminders will be scheduled (Day 3, 7 and 14 by default).{versions.data?.[0] ? ` Resume version: ${versions.data[0].filename_base}.` : ""}</p>
        <div className="mt-4 flex justify-end gap-2">
          <Button onClick={() => setConfirmApply(false)}>Cancel</Button>
          <Button variant="success" loading={busy === "apply"} onClick={apply}>Yes, I applied</Button>
        </div>
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------- overview

function Overview({ job, match, jd, onAnalyze }: { job: JobDetail; match: Match; jd: any; onAnalyze: () => void }) {
  const rows: [string, keyof Match, string][] = [
    ["Role match", "role_match", "role"], ["Skill match", "skill_match", "skills"], ["Experience match", "experience_match", "experience"],
    ["Location match", "location_match", "location"], ["Salary match", "salary_match", "salary"], ["Education match", "education_match", "education"],
    ["JD keyword match", "keyword_match", ""],
  ];
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <div className="space-y-5">
        {match && "overall" in match ? (
          <Card title={<span>Match score: {match.overall}%</span>}>
            <div className="space-y-3">
              {rows.map(([label, key, exp]) => (
                <div key={key}>
                  <div className="mb-1 flex justify-between text-xs"><span className="font-medium">{label} <span className="text-slate-400">({match.components[String(key).replace("_match", "").replace("skill", "skills").replace("keyword", "keywords")]?.weight}%)</span></span><span>{match[key] as number}%</span></div>
                  <Bar value={match[key] as number} />
                  {exp && <div className="mt-0.5 text-xs text-slate-500">{match.explanations[exp]}</div>}
                </div>
              ))}
            </div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <div>
                <div className="mb-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-400">Strong</div>
                <div className="flex flex-wrap gap-1">{match.matching_skills.length ? match.matching_skills.map((s) => <Badge key={s} tone="green">{s}</Badge>) : <span className="text-xs text-slate-400">–</span>}</div>
              </div>
              <div>
                <div className="mb-1.5 text-xs font-semibold text-rose-700 dark:text-rose-400">Missing / unclear</div>
                <div className="flex flex-wrap gap-1">{match.missing_skills.length ? match.missing_skills.map((s) => <Badge key={s} tone="red">{s}</Badge>) : <span className="text-xs text-slate-400">None</span>}</div>
              </div>
            </div>
            {match.why.length > 0 && <div className="mt-4"><div className="mb-1 text-xs font-semibold">Why this job matches</div><ul className="list-disc space-y-0.5 pl-5 text-sm">{match.why.map((w) => <li key={w}>{w}</li>)}</ul></div>}
            {match.concerns.length > 0 && <div className="mt-4"><div className="mb-1 text-xs font-semibold text-amber-700 dark:text-amber-400">Potential concerns</div><ul className="list-disc space-y-0.5 pl-5 text-sm">{match.concerns.map((w) => <li key={w}>{w}</li>)}</ul></div>}
            <div className="mt-4 rounded-lg bg-brand-50 p-3 text-sm dark:bg-brand-600/10"><b>Recommendation:</b> {match.recommendation}</div>
            <p className="mt-2 text-xs text-slate-400">{match.disclaimer}</p>
          </Card>
        ) : <Card><Empty title="Not scored yet" action={<Button onClick={onAnalyze}>Analyze</Button>} /></Card>}
        {jd && (
          <Card title="Job description analysis">
            {jd.red_flags?.length > 0 && <div className="mb-3 space-y-1">{jd.red_flags.map((f: string) => <Notice key={f} tone="warn">⚠ {f}</Notice>)}</div>}
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-slate-500">Role type</dt><dd>{jd.role_category} · {jd.seniority}</dd>
              <dt className="text-slate-500">Education</dt><dd>{jd.education || "Not specified"}</dd>
              <dt className="text-slate-500">Notice period</dt><dd>{jd.notice_period || "Not specified"}</dd>
            </dl>
            <div className="mt-3 text-xs font-semibold">Required skills</div>
            <div className="mt-1 flex flex-wrap gap-1">{jd.required_skills.map((s: string) => <Badge key={s}>{s}</Badge>)}</div>
            {jd.requirements?.length > 0 && <><div className="mt-3 text-xs font-semibold">Key requirements</div><ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{jd.requirements.map((r: string) => <li key={r}>{r}</li>)}</ul></>}
            <div className="mt-3 text-xs font-semibold">Keywords</div>
            <div className="mt-1 flex flex-wrap gap-1">{jd.keywords.map((s: string) => <Badge key={s} tone="blue">{s}</Badge>)}</div>
          </Card>
        )}
      </div>
      <Card title="Job description">
        <div className="prose-msg max-h-[70vh] overflow-y-auto text-slate-700 dark:text-slate-300">{job.description || "No description saved. Paste it via Job Search → Import."}</div>
        {job.skills.length > 0 && <div className="mt-4 flex flex-wrap gap-1 border-t border-slate-100 pt-3 dark:border-slate-800">{job.skills.map((s) => <Badge key={s}>{s}</Badge>)}</div>}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- ATS

export function AtsView({ ats }: { ats: AtsResult }) {
  const bars: [string, number | undefined][] = [
    ["Keyword match", ats.keyword_coverage], ["Skill coverage", ats.skill_coverage], ["Experience relevance", ats.experience_relevance],
    ["Job title relevance", ats.job_title_relevance], ["Formatting compatibility", ats.formatting_compatibility],
    ["Section completeness", ats.section_completeness], ["Readability", ats.readability],
  ];
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title="ATS compatibility estimate">
        <div className="flex items-center gap-5">
          <ScoreRing score={ats.ats_score} label="ATS est." />
          <div className="flex-1 space-y-2.5">
            {bars.filter(([, v]) => v !== undefined).map(([l, v]) => (
              <div key={l}><div className="mb-0.5 flex justify-between text-xs"><span>{l}</span><span>{v}%</span></div><Bar value={v!} /></div>
            ))}
          </div>
        </div>
        <p className="mt-4 text-xs text-slate-400">{ats.disclaimer}</p>
      </Card>
      {ats.relevant_keywords && (
        <Card title="Keywords">
          <div className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">Relevant keywords found ({ats.relevant_keywords.length})</div>
          <div className="mt-1 flex flex-wrap gap-1">{ats.relevant_keywords.map((k) => <Badge key={k} tone="green">{k}</Badge>)}</div>
          <div className="mt-3 text-xs font-semibold text-rose-700 dark:text-rose-400">Missing keywords ({ats.missing_keywords!.length})</div>
          <div className="mt-1 flex flex-wrap gap-1">{ats.missing_keywords!.map((k) => <Badge key={k} tone="red">{k}</Badge>)}</div>
          <div className="mt-3 text-xs font-semibold">Skills already present</div>
          <div className="mt-1 flex flex-wrap gap-1">{ats.skills_present!.map((k) => <Badge key={k}>{k}</Badge>)}</div>
          <p className="mt-3 text-xs text-slate-500">Add a missing keyword only if it's true for you, and back it with a bullet. Keyword stuffing hurts with human reviewers.</p>
        </Card>
      )}
      {ats.important_requirements && ats.important_requirements.length > 0 && (
        <Card title="Potentially important JD requirements"><ul className="list-disc space-y-1 pl-5 text-sm">{ats.important_requirements.map((r) => <li key={r}>{r}</li>)}</ul></Card>
      )}
      <Card title="Issues">
        {[["Formatting", ats.formatting_issues.map((i) => `${i.issue} → ${i.fix}`)], ["Sections", ats.section_issues], ["Readability", ats.readability_issues]].map(([title, items]) => (
          <div key={title as string} className="mb-3">
            <div className="text-xs font-semibold">{title as string}</div>
            {(items as string[]).length ? <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">{(items as string[]).map((i) => <li key={i}>{i}</li>)}</ul> : <p className="text-sm text-emerald-600">No issues found</p>}
          </div>
        ))}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- resume versions

export function ResumePreview({ r }: { r: ResumeVersion["content"] }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 text-[13px] leading-relaxed text-slate-800 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200">
      <div className="text-center"><div className="text-lg font-bold">{r.name}</div><div>{r.headline}</div>
        <div className="text-xs text-slate-500">{Object.values(r.contact || {}).filter(Boolean).join(" | ")}</div></div>
      {r.summary && <><h4 className="mt-4 border-b text-xs font-bold uppercase tracking-wide text-[#1f3a5f] dark:text-sky-300">Professional Summary</h4><p className="mt-1">{r.summary}</p></>}
      <h4 className="mt-4 border-b text-xs font-bold uppercase tracking-wide text-[#1f3a5f] dark:text-sky-300">Skills</h4>
      {r.skills_core?.length > 0 && <p className="mt-1"><b>Core:</b> {r.skills_core.join(", ")}</p>}
      {r.skills?.length > 0 && <p className="mt-1">{r.skills_core?.length ? <b>Additional: </b> : null}{r.skills.join(", ")}</p>}
      {r.experience?.length > 0 && <h4 className="mt-4 border-b text-xs font-bold uppercase tracking-wide text-[#1f3a5f] dark:text-sky-300">Professional Experience</h4>}
      {r.experience?.map((e, i) => (
        <div key={i} className="mt-2"><div className="font-semibold">{[e.designation, e.company, e.location].filter(Boolean).join(" | ")} <span className="font-normal text-slate-500">{e.duration}</span></div>
          <ul className="list-disc pl-5">{e.bullets.map((b) => <li key={b}>{b}</li>)}</ul></div>
      ))}
      {r.projects?.length > 0 && <h4 className="mt-4 border-b text-xs font-bold uppercase tracking-wide text-[#1f3a5f] dark:text-sky-300">Projects</h4>}
      {r.projects?.map((p, i) => <div key={i} className="mt-2"><div className="font-semibold">{p.name}{p.tech.length ? ` | ${p.tech.join(", ")}` : ""}</div><ul className="list-disc pl-5">{p.bullets.map((b) => <li key={b}>{b}</li>)}</ul></div>)}
      {r.education?.length > 0 && <><h4 className="mt-4 border-b text-xs font-bold uppercase tracking-wide text-[#1f3a5f] dark:text-sky-300">Education</h4>
        {r.education.map((e, i) => <p key={i} className="mt-1">{[e.degree, e.institution, e.year].filter(Boolean).join(", ")}{e.score ? ` | ${e.score}` : ""}</p>)}</>}
      {r.certifications?.length > 0 && <><h4 className="mt-4 border-b text-xs font-bold uppercase tracking-wide text-[#1f3a5f] dark:text-sky-300">Certifications</h4><ul className="list-disc pl-5">{r.certifications.map((c) => <li key={c}>{c}</li>)}</ul></>}
    </div>
  );
}

function ResumeVersions({ versions, loading, onTailor, busy, hasResume, onDeleted }: { versions: ResumeVersion[]; loading: boolean; onTailor: () => void; busy: boolean; hasResume: boolean; onDeleted: () => void }) {
  const [sel, setSel] = useState(0);
  if (loading) return <Skeleton />;
  if (!versions.length) return <Card><Empty title="No tailored resume for this job yet" text="Creates a job-specific version from your master resume. Nothing is invented; skills you don't have are listed, not added."
    action={<Button variant="primary" loading={busy} disabled={!hasResume} onClick={onTailor}>Tailor Resume</Button>} /></Card>;
  const v = versions[Math.min(sel, versions.length - 1)];
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <ResumePreview r={v.content} />
      <div className="space-y-4">
        <Card title="Versions" action={<Button loading={busy} onClick={onTailor} icon={<Sparkles className="h-4 w-4" />}>New version</Button>} bodyClass="p-2">
          {versions.map((x, i) => (
            <button key={x.id} onClick={() => setSel(i)} className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${i === sel ? "bg-brand-50 dark:bg-brand-600/15" : "hover:bg-slate-50 dark:hover:bg-slate-800"}`}>
              <span className="truncate">{x.filename_base}</span><ScoreBadge score={x.ats_score} label="ATS" />
            </button>
          ))}
        </Card>
        <Card title={<span className="block break-all">{v.filename_base}</span>}>
          <div className="flex flex-wrap gap-2">
            <a href={api.downloadUrl(v.id, "docx")}><Button variant="primary" icon={<Download className="h-4 w-4" />}>DOCX</Button></a>
            <a href={api.downloadUrl(v.id, "pdf")}><Button icon={<Download className="h-4 w-4" />}>PDF</Button></a>
            <Button variant="ghost" icon={<Trash2 className="h-4 w-4" />} aria-label="Delete version" onClick={async () => { if (confirm("Delete this version?")) { await api.deleteVersion(v.id); setSel(0); onDeleted(); } }} />
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-1 text-sm">
            <dt className="text-slate-500">Version</dt><dd>v{v.version}</dd>
            <dt className="text-slate-500">Created</dt><dd>{fmtDate(v.created_at)}</dd>
            <dt className="text-slate-500">ATS estimate</dt><dd>{v.ats_score}%</dd>
            <dt className="text-slate-500">AI used</dt><dd>{v.content.ai_used ? "Yes (verified)" : "No (rules)"}</dd>
          </dl>
          {v.keywords_added.length > 0 && <div className="mt-3"><div className="text-xs font-semibold">Keywords surfaced from your profile</div><div className="mt-1 flex flex-wrap gap-1">{v.keywords_added.map((k) => <Badge key={k} tone="green">{k}</Badge>)}</div></div>}
          <div className="mt-3 text-xs font-semibold">What changed</div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-slate-600 dark:text-slate-400">{v.changes.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- messages

export function MessageEditor({ comm, onSaved, onRegenerate, regenerating }: { comm: Communication; onSaved: () => void; onRegenerate?: () => void; regenerating?: boolean }) {
  const toast = useToast();
  const [subject, setSubject] = useState(comm.subject);
  const [body, setBody] = useState(comm.body);
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [links, setLinks] = useState<{ mailto: string; whatsapp: string; linkedin: string } | null>(null);
  const dirty = subject !== comm.subject || body !== comm.body;
  const limit = comm.channel === "linkedin_note" ? 300 : 0;
  useEffect(() => { api.commLinks(comm.id).then(setLinks).catch(() => {}); }, [comm.id, comm.body, comm.subject]);

  const saveEdit = async () => {
    setSaving(true);
    try { await api.updateCommunication(comm.id, { subject, body }); toast.success("Saved"); onSaved(); } catch (e) { toast.error((e as Error).message); } finally { setSaving(false); }
  };
  const markSent = async () => {
    try {
      if (dirty) await api.updateCommunication(comm.id, { subject, body });
      await api.updateCommunication(comm.id, { mark_sent: true, confirm: true });
      toast.success("Recorded as sent");
      setConfirm(false);
      onSaved();
    } catch (e) { toast.error((e as Error).message); }
  };
  return (
    <Card title={<span className="flex items-center gap-2">{CHANNEL_LABELS[comm.channel] ?? comm.channel}
      <Badge tone={comm.status === "sent" ? "green" : "slate"}>{comm.status === "sent" ? `Sent ${fmtDate(comm.sent_at)}` : "Draft"}</Badge>
      <Badge tone={comm.generated_by === "template" ? "slate" : "violet"}>{comm.generated_by === "template" ? "Template" : "AI (verified)"}</Badge></span>}
      action={onRegenerate && <Button variant="ghost" loading={regenerating} onClick={onRegenerate} icon={<Sparkles className="h-4 w-4" />}>Regenerate</Button>}>
      {comm.subject !== "" && <Field label="Subject"><input className="input mb-3" value={subject} onChange={(e) => setSubject(e.target.value)} /></Field>}
      <textarea aria-label="Message body" className="input min-h-[260px] font-[inherit] leading-relaxed" value={body} onChange={(e) => setBody(e.target.value)} />
      <div className="mt-1 flex justify-between text-xs text-slate-400">
        <span>Edit freely. Nothing is sent automatically.</span>
        <span className={limit && body.length > limit ? "font-semibold text-rose-600" : ""}>{body.length}{limit ? ` / ${limit}` : ""} characters</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {dirty && <Button variant="primary" loading={saving} disabled={!!limit && body.length > limit} onClick={saveEdit}>Save changes</Button>}
        <CopyButton text={comm.subject && comm.channel.includes("email") ? `Subject: ${subject}\n\n${body}` : body} />
        {links && (comm.channel === "email" || comm.channel === "followup_email" || comm.channel === "cover_letter") && <a href={links.mailto}><Button icon={<Mail className="h-4 w-4" />}>Open in email app</Button></a>}
        {links && (comm.channel === "whatsapp" || comm.channel === "followup_message") && <a href={links.whatsapp} target="_blank" rel="noreferrer"><Button icon={<MessageCircle className="h-4 w-4" />}>Open WhatsApp</Button></a>}
        {links?.linkedin && comm.channel.startsWith("linkedin") && <a href={links.linkedin} target="_blank" rel="noreferrer"><Button icon={<Linkedin className="h-4 w-4" />}>Open LinkedIn profile</Button></a>}
        {comm.status !== "sent" && comm.channel !== "cover_letter" && <Button variant="success" icon={<Send className="h-4 w-4" />} onClick={() => setConfirm(true)}>Mark as sent</Button>}
      </div>
      <Modal open={confirm} onClose={() => setConfirm(false)} title="Did you send this message?">
        <p className="text-sm text-slate-600 dark:text-slate-300">JobPilot doesn't send messages. Confirm only after <b>you</b> sent it from your own email / WhatsApp / LinkedIn. This updates the application to "HR Contacted".</p>
        <div className="mt-4 flex justify-end gap-2"><Button onClick={() => setConfirm(false)}>Cancel</Button><Button variant="success" onClick={markSent}>Yes, I sent it</Button></div>
      </Modal>
    </Card>
  );
}

// ---------------------------------------------------------------- track

function TrackPanel({ job, onChange }: { job: JobDetail; onChange: () => void }) {
  const toast = useToast();
  const appId = job.application_id;
  const detail = useAsync(() => (appId ? api.application(appId) : Promise.resolve(null)), [appId, job.application_status]);
  const contacts = useAsync(() => api.contacts({ job_id: job.id }), [job.id]);
  const [notes, setNotes] = useState("");
  const [showContact, setShowContact] = useState(false);
  useEffect(() => { setNotes(detail.data?.application.notes ?? ""); }, [detail.data]);

  const update = async (b: Record<string, unknown>) => {
    try {
      if (!appId) await api.createApplication({ job_id: job.id, status: (b.status as string) ?? "Saved" });
      else await api.updateApplication(appId, b);
      toast.success("Application updated");
      onChange();
      detail.reload(true);
    } catch (e) { toast.error((e as Error).message); }
  };

  const a = detail.data?.application;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title="Application">
        {!appId ? (
          <Empty title="Not tracked yet" action={<Button variant="primary" onClick={() => update({ status: "Saved" })}>Track this job</Button>} />
        ) : !a ? <Skeleton rows={3} /> : (
          <div className="space-y-3">
            <Field label="Status">
              <select className="input" value={a.status} onChange={(e) => update({ status: e.target.value })}>{APP_STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
            </Field>
            <dl className="grid grid-cols-2 gap-1 text-sm">
              <dt className="text-slate-500">Application date</dt><dd>{fmtDate(a.applied_date)}</dd>
              <dt className="text-slate-500">Last follow-up</dt><dd>{fmtDate(a.last_followup_date)}</dd>
              <dt className="text-slate-500">Next follow-up</dt><dd>{fmtDate(a.next_followup_date)}</dd>
              <dt className="text-slate-500">Resume version</dt><dd className="truncate">{a.resume_version_name || "–"}</dd>
              <dt className="text-slate-500">Communication sent</dt><dd>{a.communication_sent.map((c) => CHANNEL_LABELS[c] ?? c).join(", ") || "–"}</dd>
            </dl>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={a.response_received} onChange={(e) => update({ response_received: e.target.checked })} /> Employer responded</label>
            <Field label="Notes"><textarea className="input min-h-[90px]" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
            {notes !== a.notes && <Button variant="primary" onClick={() => update({ notes })}>Save notes</Button>}
            {detail.data!.followups.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold">Follow-up schedule</div>
                <ul className="space-y-1 text-sm">{detail.data!.followups.map((f) => (
                  <li key={f.id} className="flex items-center justify-between rounded-md bg-slate-50 px-2 py-1 dark:bg-slate-800/60">
                    <span>Day {f.day_offset}: {f.label}</span>
                    <span className="flex items-center gap-2 text-xs">{fmtDate(f.due_date)} <Badge tone={f.status === "done" ? "green" : f.status === "skipped" ? "slate" : f.overdue ? "red" : "blue"}>{f.status}</Badge></span>
                  </li>))}</ul>
              </div>
            )}
          </div>
        )}
      </Card>
      <Card title="HR contacts (public info only)" action={<Button icon={<UserPlus className="h-4 w-4" />} onClick={() => setShowContact(true)}>Add</Button>}>
        {contacts.data?.length ? (
          <ul className="space-y-2 text-sm">{contacts.data.map((c) => (
            <li key={c.id} className="rounded-lg border border-slate-100 p-2.5 dark:border-slate-800">
              <div className="font-medium">{c.name || "Unnamed"} <span className="text-xs text-slate-500">· {c.role_title}</span></div>
              <div className="text-xs text-slate-500">{[c.email, c.phone, c.linkedin_url].filter(Boolean).join(" · ") || "No contact details"}</div>
              {c.source_note && <div className="text-xs text-slate-400">Source: {c.source_note}</div>}
            </li>))}</ul>
        ) : <Empty title="No contacts" text="Add the recruiter or HR contact if it's publicly listed (job post, careers page, their public LinkedIn)." />}
        {(job.hr_name || job.hr_email) && <p className="mt-3 text-xs text-slate-500">From posting: {job.hr_name} {job.hr_email}</p>}
      </Card>
      <ContactModal open={showContact} onClose={() => setShowContact(false)} jobId={job.id} company={job.company} onSaved={() => { contacts.reload(true); setShowContact(false); }} />
    </div>
  );
}

export function ContactModal({ open, onClose, jobId, company, onSaved, existing }: { open: boolean; onClose: () => void; jobId?: number | null; company?: string; onSaved: () => void; existing?: Contact | null }) {
  const toast = useToast();
  const empty = { name: "", role_title: "HR", email: "", phone: "", linkedin_url: "", career_page: "", source_note: "", notes: "", company: company ?? "" };
  const [f, setF] = useState(empty);
  useEffect(() => { if (open) setF(existing ? { ...empty, ...existing } : empty); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [open, existing]);
  return (
    <Modal open={open} onClose={onClose} title={existing ? "Edit contact" : "Add HR contact"}>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={async (e) => {
        e.preventDefault();
        try {
          if (existing) await api.updateContact(existing.id, { ...f, job_id: existing.job_id });
          else await api.createContact({ ...f, job_id: jobId ?? null });
          toast.success("Contact saved");
          onSaved();
        } catch (err) { toast.error((err as Error).message); }
      }}>
        <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Role"><select className="input" value={f.role_title} onChange={(e) => setF({ ...f, role_title: e.target.value })}>{["HR", "Recruiter", "Hiring Manager", "Talent Acquisition", "Other"].map((r) => <option key={r}>{r}</option>)}</select></Field>
        <Field label="Company"><input className="input" value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} /></Field>
        <Field label="Email"><input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Phone / WhatsApp"><input className="input" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label="LinkedIn URL"><input className="input" value={f.linkedin_url} onChange={(e) => setF({ ...f, linkedin_url: e.target.value })} /></Field>
        <Field label="Career page"><input className="input" value={f.career_page} onChange={(e) => setF({ ...f, career_page: e.target.value })} /></Field>
        <Field label="Where you found it" hint="e.g. job post, company site"><input className="input" value={f.source_note} onChange={(e) => setF({ ...f, source_note: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Notice>Only add contact details that are publicly shared for hiring. Don't add private numbers or scraped personal data.</Notice></div>
        <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" onClick={onClose}>Cancel</Button><Button variant="primary" type="submit">Save</Button></div>
      </form>
    </Modal>
  );
}
