import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { RefreshCw, Search, SlidersHorizontal } from "lucide-react";
import { api } from "../lib/api";
import { useAsync, useDebounced } from "../lib/hooks";
import { JobRow } from "../components/JobTable";
import { useToast } from "../components/Toast";
import { Button, Card, Empty, ErrorBox, PageHeader, Pagination, Skeleton } from "../components/ui";

const ROLES = ["Data Analyst", "Business Analyst", "BI Analyst", "MIS Executive", "Reporting Analyst", "Operations Analyst",
  "Financial Analyst", "Data Scientist", "Other"];
const STATUSES = ["New", "Saved", "Shortlisted", "Applied", "Ignored"];

export default function JobMatches() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const p = Object.fromEntries(params.entries());
  const page = Number(p.page || 1);
  const q = useDebounced(p.q || "");
  const sources = useAsync(() => api.sources());
  const [showFilters, setShowFilters] = useState(() => window.innerWidth >= 768);

  const query = {
    q, role: p.role, location: p.location, source: p.source, status: p.status, min_score: p.min_score,
    max_experience: p.max_experience, min_salary_monthly: p.min_salary_monthly, posted_within_days: p.posted_within_days,
    remote: p.remote, sort: p.sort || "match_score", order: p.order || "desc", page, page_size: 20,
  };
  const jobs = useAsync(() => api.jobs(query), [JSON.stringify(query)]);

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    if (k !== "page") next.delete("page");
    setParams(next, { replace: true });
  };
  const sel = (k: string, label: string, options: [string, string][]) => (
    <select aria-label={label} className="input" value={p[k] || ""} onChange={(e) => set(k, e.target.value)}>
      <option value="">{label}</option>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
  const active = ["role", "location", "source", "status", "min_score", "max_experience", "min_salary_monthly", "posted_within_days", "remote", "q"].some((k) => p[k]);

  return (
    <div className="space-y-5">
      <PageHeader title="Job Matches" subtitle="Every job, scored against your profile and resume. The score helps you prioritise; it doesn't predict selection."
        actions={<>
          <Button icon={<RefreshCw className="h-4 w-4" />} onClick={async () => { const r = await api.rescore(); toast.success(`Re-scored ${r.rescored} jobs`); jobs.reload(); }}>Re-score</Button>
          <Button variant="primary" icon={<Search className="h-4 w-4" />} onClick={() => nav("/search?run=1")}>Find Jobs</Button>
        </>} />

      <Card bodyClass="p-3">
        <button className="mb-2 flex items-center gap-2 text-xs font-medium text-slate-500" aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>
          <SlidersHorizontal className="h-3.5 w-3.5" /> Filters {!showFilters && "(tap to show)"}
        </button>
        <div className={`${showFilters ? "grid" : "hidden"} gap-2 sm:grid-cols-2 md:grid-cols-4 xl:grid-cols-6`}>
          <input className="input xl:col-span-2" placeholder="Title, company or keyword" aria-label="Keyword" value={p.q || ""} onChange={(e) => set("q", e.target.value)} />
          {sel("role", "All roles", ROLES.map((r) => [r, r]))}
          <input className="input" placeholder="Location (e.g. Noida)" aria-label="Location" value={p.location || ""} onChange={(e) => set("location", e.target.value)} />
          {sel("source", "All sources", (sources.data ?? []).map((s) => [s.key, s.name]).concat([["manual", "Manual"], ["url_import", "URL import"], ["import", "File import"]]) as [string, string][])}
          {sel("status", "Any status", STATUSES.map((s) => [s, s]))}
          {sel("min_score", "Any match score", [["50", "50%+"], ["60", "60%+"], ["70", "70%+"], ["75", "75%+"], ["80", "80%+"], ["90", "90%+"]])}
          {sel("max_experience", "Any experience", [["2", "≤ 2 yrs required"], ["3", "≤ 3 yrs"], ["4", "≤ 4 yrs"], ["5", "≤ 5 yrs"], ["7", "≤ 7 yrs"]])}
          {sel("min_salary_monthly", "Any salary", [["35000", "≥ ₹35k/mo"], ["42000", "≥ ₹42k/mo"], ["50000", "≥ ₹50k/mo"], ["60000", "≥ ₹60k/mo"], ["75000", "≥ ₹75k/mo"]])}
          {sel("posted_within_days", "Any date", [["1", "Last 24 hours"], ["3", "Last 3 days"], ["7", "Last 7 days"], ["30", "Last 30 days"]])}
          {sel("remote", "Remote or on-site", [["true", "Remote only"], ["false", "On-site / hybrid"]])}
          {sel("sort", "Sort: best match", [["match_score", "Sort: best match"], ["posted_date", "Sort: newest posted"], ["created_at", "Sort: recently found"], ["salary_max", "Sort: salary"], ["company", "Sort: company"]])}
        </div>
        {active && <button className="mt-2 text-xs text-brand-600" onClick={() => setParams({}, { replace: true })}>Clear filters</button>}
      </Card>

      <Card bodyClass="p-2">
        {jobs.loading ? <Skeleton rows={6} /> : jobs.error ? <ErrorBox message={jobs.error} onRetry={() => jobs.reload()} /> :
          jobs.data!.items.length === 0 ? (
            <Empty title={active ? "No jobs match these filters" : "No jobs yet"}
              text={active ? "Try widening the filters." : "Run a search or import a job to get started."}
              action={active ? <Button onClick={() => setParams({})}>Clear filters</Button> : <Button variant="primary" onClick={() => nav("/search?run=1")}>Find Jobs</Button>} />
          ) : (
            <>
              {jobs.data!.items.map((j) => <JobRow key={j.id} job={j} />)}
              <div className="px-2"><Pagination page={page} pageSize={20} total={jobs.data!.total} onPage={(n) => set("page", String(n))} /></div>
            </>
          )}
      </Card>
    </div>
  );
}
