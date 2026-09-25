import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, Briefcase, CalendarClock, Flame, MessageSquare, Search, Sparkles, Target, Trophy, Users } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { BarViz } from "../components/Charts";
import { JobRow } from "../components/JobTable";
import { Badge, Button, Card, Empty, ErrorBox, Notice, PageHeader, Skeleton, fmtDate } from "../components/ui";

function Stat({ label, value, icon: I, hint, to }: { label: string; value: string | number; icon: any; hint?: string; to?: string }) {
  const body = (
    <div className="card flex items-center gap-3 p-4 transition hover:shadow-md">
      <div className="rounded-lg bg-brand-50 p-2.5 text-brand-600 dark:bg-brand-600/15 dark:text-brand-100"><I className="h-5 w-5" /></div>
      <div className="min-w-0">
        <div className="text-2xl font-semibold text-slate-900 dark:text-white">{value}</div>
        <div className="truncate text-xs text-slate-500">{label}{hint ? ` · ${hint}` : ""}</div>
      </div>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export default function Dashboard() {
  const nav = useNavigate();
  const dash = useAsync(() => api.dashboard());
  const analytics = useAsync(() => api.analytics());
  const top = useAsync(() => api.jobs({ sort: "match_score", order: "desc", page_size: 6, status: "New,Saved,Shortlisted" }));
  const due = useAsync(() => api.followups({ status: "pending", due_only: true }));
  const resumes = useAsync(() => api.resumes());

  if (dash.error) return <ErrorBox message={dash.error} onRetry={() => dash.reload()} />;
  const d = dash.data;
  const a = analytics.data;

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" subtitle="Your job search at a glance"
        actions={<Button variant="primary" icon={<Search className="h-4 w-4" />} onClick={() => nav("/search?run=1")}>Find Jobs</Button>} />

      {resumes.data && resumes.data.length === 0 && (
        <Notice tone="warn">
          <b>Upload your master resume</b> to unlock ATS analysis, tailored resumes and application kits.{" "}
          <Link className="underline" to="/resume">Go to Resume →</Link>
        </Notice>
      )}

      {!d ? <Skeleton rows={2} /> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Jobs found today" value={d.jobs_found_today} icon={Sparkles} hint={`${d.jobs_total} total`} to="/matches" />
          <Stat label="Relevant jobs" value={d.relevant_jobs} icon={Target} hint={`≥ ${d.thresholds.relevant}%`} to={`/matches?min_score=${d.thresholds.relevant}`} />
          <Stat label="High match jobs" value={d.high_match_jobs} icon={Flame} hint={`≥ ${d.thresholds.high}%`} to={`/matches?min_score=${d.thresholds.high}`} />
          <Stat label="Applications" value={d.applications} icon={Briefcase} to="/applications" />
          <Stat label="HR contacts" value={d.hr_contacts} icon={Users} to="/outreach" />
          <Stat label="Interviews" value={d.interviews} icon={MessageSquare} to="/applications?status=Interview,Assessment" />
          <Stat label="Offers" value={d.offers} icon={Trophy} to="/applications?status=Offer" />
          <Stat label="Response rate" value={`${d.response_rate}%`} icon={CalendarClock} hint="of applications" to="/analytics" />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2" title="Top matches" action={<Link to="/matches" className="text-xs text-brand-600">View all</Link>} bodyClass="p-2">
          {top.loading ? <Skeleton /> : top.error ? <ErrorBox message={top.error} /> : top.data?.items.length ? (
            top.data.items.map((j) => <JobRow key={j.id} job={j} />)
          ) : (
            <Empty title="No jobs yet" text="Run a search to discover jobs, or import one you found yourself."
              action={<Button variant="primary" onClick={() => nav("/search?run=1")}>Find Jobs</Button>} />
          )}
        </Card>
        <Card title={<span className="flex items-center gap-2">Follow-ups due {due.data && due.data.length > 0 && <Badge tone="red">{due.data.length}</Badge>}</span>}
          action={<Link to="/followups" className="text-xs text-brand-600">All</Link>}>
          {due.loading ? <Skeleton rows={3} /> : due.data?.length ? (
            <ul className="space-y-2">
              {due.data.slice(0, 6).map((f) => (
                <li key={f.id} className="rounded-lg border border-slate-100 p-2.5 text-sm dark:border-slate-800">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{f.label}</span>
                    {f.overdue && <Badge tone="red"><AlertTriangle className="mr-1 h-3 w-3" />Overdue</Badge>}
                  </div>
                  <div className="text-xs text-slate-500">{f.job_title} · {f.company} · due {fmtDate(f.due_date)}</div>
                </li>
              ))}
            </ul>
          ) : <Empty title="Nothing due" text="Reminders appear here after you mark a job as applied." />}
        </Card>
      </div>

      {a && (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          <Card title="Applications by week"><BarViz data={a.weekly.map((w: any) => ({ ...w, week: fmtDate(w.week).replace(/ \d{4}$/, "") }))} x="week" y="applications" valueLabel="Applications" /></Card>
          <Card title="Jobs by source"><BarViz data={a.jobs_by_source} x="name" y="count" horizontal valueLabel="Jobs" labels /></Card>
          <Card title="Jobs by role"><BarViz data={a.jobs_by_role} x="name" y="count" horizontal valueLabel="Jobs" labels /></Card>
          <Card title="Match-score distribution"><BarViz data={a.match_distribution} x="range" y="count" valueLabel="Jobs" labels /></Card>
          <Card title="Application funnel"><BarViz data={a.funnel} x="stage" y="count" horizontal valueLabel="Jobs" labels /></Card>
          <Card title="Response rate by source">
            <BarViz data={a.source_response} x="name" y="response_rate" horizontal suffix="%" valueLabel="Response rate" labels />
            <p className="mt-2 text-xs text-slate-400">{a.note}</p>
          </Card>
        </div>
      )}
    </div>
  );
}
