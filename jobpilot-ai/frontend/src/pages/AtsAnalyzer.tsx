import { useState } from "react";
import { Link } from "react-router-dom";
import { Gauge } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import type { AtsResult } from "../lib/types";
import { useToast } from "../components/Toast";
import { Button, Card, Empty, Field, Notice, PageHeader, Skeleton, Tabs } from "../components/ui";
import { AtsView } from "./JobDetail";

export default function AtsAnalyzer() {
  const toast = useToast();
  const resumes = useAsync(() => api.resumes());
  const jobs = useAsync(() => api.jobs({ sort: "match_score", page_size: 100 }));
  const [mode, setMode] = useState<"job" | "paste" | "general">("job");
  const [resumeId, setResumeId] = useState<number | "">("");
  const [jobId, setJobId] = useState<number | "">("");
  const [jd, setJd] = useState("");
  const [title, setTitle] = useState("");
  const [result, setResult] = useState<AtsResult | null>(null);
  const [busy, setBusy] = useState(false);

  if (resumes.loading) return <Skeleton />;
  if (!resumes.data?.length) return (
    <div><PageHeader title="ATS Analyzer" /><Card><Empty title="Upload a resume first" action={<Link to="/resume"><Button variant="primary">Go to Resume</Button></Link>} /></Card></div>
  );

  const run = async () => {
    setBusy(true);
    try {
      const body: Record<string, any> = { resume_id: resumeId || undefined };
      if (mode === "job") { if (!jobId) throw new Error("Choose a job"); body.job_id = jobId; }
      if (mode === "paste") { if (jd.trim().length < 50) throw new Error("Paste the full job description (at least a few lines)"); body.jd_text = jd; body.job_title = title; }
      setResult(await api.analyzeResume(body));
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="ATS Analyzer" subtitle="An ATS compatibility estimate: keyword coverage, formatting, sections and readability. No tool can guarantee an ATS pass." />
      <Card>
        <div className="grid gap-4 md:grid-cols-[1fr_2fr]">
          <Field label="Resume">
            <select className="input" value={resumeId} onChange={(e) => setResumeId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Master resume</option>
              {resumes.data.map((r) => <option key={r.id} value={r.id}>{r.filename}{r.is_master ? " (master)" : ""}</option>)}
            </select>
          </Field>
          <div>
            <Tabs tabs={[{ id: "job", label: "Against a saved job" }, { id: "paste", label: "Paste a JD" }, { id: "general", label: "General check" }]} value={mode} onChange={setMode} />
            <div className="pt-3">
              {mode === "job" && (
                <select className="input" aria-label="Job" value={jobId} onChange={(e) => setJobId(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">Choose a job…</option>
                  {jobs.data?.items.map((j) => <option key={j.id} value={j.id}>{j.title} · {j.company} ({j.match_score ?? "–"}%)</option>)}
                </select>
              )}
              {mode === "paste" && (
                <div className="space-y-2">
                  <input className="input" placeholder="Job title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
                  <textarea className="input min-h-[160px]" placeholder="Paste the job description" value={jd} onChange={(e) => setJd(e.target.value)} />
                </div>
              )}
              {mode === "general" && <Notice>Checks formatting, sections and readability without a job description.</Notice>}
            </div>
          </div>
        </div>
        <div className="mt-4"><Button variant="primary" icon={<Gauge className="h-4 w-4" />} loading={busy} onClick={run}>Analyze</Button></div>
      </Card>
      {result && <AtsView ats={result} />}
    </div>
  );
}
