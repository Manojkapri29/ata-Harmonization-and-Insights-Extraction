import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpDown, Download } from "lucide-react";
import { api } from "../lib/api";
import { useAsync, useDebounced } from "../lib/hooks";
import { APP_STATUSES, type Application } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, ScoreBadge, Skeleton, cx, fmtDate } from "../components/ui";

const TONE: Record<string, "slate" | "blue" | "violet" | "green" | "amber" | "red"> = {
  Saved: "slate", Shortlisted: "slate", "Resume Tailored": "blue", Applied: "violet", "HR Contacted": "violet",
  Interview: "green", Assessment: "green", Offer: "green", Rejected: "red", Closed: "slate",
};

export default function Applications() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const [q, setQ] = useState("");
  const dq = useDebounced(q);
  const apps = useAsync(() => api.applications({ status, q: dq }), [status, dq]);
  const all = useAsync(() => api.applications(), []);
  const [sort, setSort] = useState<{ key: keyof Application; dir: 1 | -1 }>({ key: "updated_at", dir: -1 });

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    (all.data ?? []).forEach((a) => { c[a.status] = (c[a.status] ?? 0) + 1; });
    return c;
  }, [all.data]);

  const rows = useMemo(() => [...(apps.data ?? [])].sort((a, b) => {
    const x = a[sort.key] ?? "", y = b[sort.key] ?? "";
    return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
  }), [apps.data, sort]);

  const update = async (a: Application, s: string) => {
    try {
      await api.updateApplication(a.id, { status: s });
      toast.success(`${a.job_title}: ${s}${s === "Applied" ? " — follow-ups scheduled" : ""}`);
      apps.reload(true); all.reload(true);
    } catch (e) { toast.error((e as Error).message); }
  };
  const th = (label: string, key: keyof Application) => (
    <th className="px-3 py-2"><button className="inline-flex items-center gap-1" onClick={() => setSort((s) => ({ key, dir: s.key === key ? (-s.dir as 1 | -1) : -1 }))}>{label}<ArrowUpDown className="h-3 w-3" /></button></th>
  );

  return (
    <div className="space-y-5">
      <PageHeader title="Applications" subtitle="Track every application from saved to offer."
        actions={<a href={api.exportUrl("applications", "xlsx")}><Button icon={<Download className="h-4 w-4" />}>Export Excel</Button></a>} />
      <div className="flex flex-wrap gap-1.5">
        {["", ...APP_STATUSES].map((s) => (
          <button key={s || "all"} onClick={() => { const n = new URLSearchParams(params); if (s) n.set("status", s); else n.delete("status"); setParams(n, { replace: true }); }}
            className={cx("rounded-full border px-3 py-1 text-xs font-medium", status === s ? "border-brand-600 bg-brand-600 text-white" : "border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800")}>
            {s || "All"} <span className="opacity-70">{s ? counts[s] ?? 0 : all.data?.length ?? 0}</span>
          </button>
        ))}
      </div>
      <Card bodyClass="p-0">
        <div className="border-b border-slate-100 p-3 dark:border-slate-800"><input className="input max-w-sm" placeholder="Search role or company" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search applications" /></div>
        {apps.loading ? <div className="p-4"><Skeleton /></div> : apps.error ? <div className="p-4"><ErrorBox message={apps.error} onRetry={() => apps.reload()} /></div> : !rows.length ? (
          <Empty title="No applications here" text="Save a job or mark one as applied from its detail page." action={<Link to="/matches"><Button variant="primary">Browse matches</Button></Link>} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50">
                <tr>{th("Role", "job_title")}{th("Company", "company")}<th className="px-3 py-2">Match</th>{th("Status", "status")}{th("Applied", "applied_date")}{th("Last follow-up", "last_followup_date")}{th("Next follow-up", "next_followup_date")}<th className="px-3 py-2">Resume version</th><th className="px-3 py-2">Sent</th></tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-3 py-2"><Link to={`/jobs/${a.job_id}?tab=track`} className="font-medium text-brand-600 hover:underline">{a.job_title}</Link><div className="text-xs text-slate-500">{a.location}</div></td>
                    <td className="px-3">{a.company}</td>
                    <td className="px-3"><ScoreBadge score={a.match_score} /></td>
                    <td className="px-3">
                      <select aria-label="Status" className="rounded-md border border-slate-300 bg-transparent px-2 py-1 text-xs dark:border-slate-700" value={a.status} onChange={(e) => update(a, e.target.value)}>
                        {APP_STATUSES.map((s) => <option key={s}>{s}</option>)}
                      </select>
                      <div className="mt-1"><Badge tone={TONE[a.status]}>{a.status}</Badge></div>
                    </td>
                    <td className="whitespace-nowrap px-3">{fmtDate(a.applied_date)}</td>
                    <td className="whitespace-nowrap px-3">{fmtDate(a.last_followup_date)}</td>
                    <td className="whitespace-nowrap px-3">{a.next_followup_date ? <span className={a.next_followup_date <= new Date().toISOString().slice(0, 10) ? "font-semibold text-rose-600" : ""}>{fmtDate(a.next_followup_date)}</span> : "–"}</td>
                    <td className="max-w-[200px] truncate px-3 text-xs" title={a.resume_version_name}>{a.resume_version_name || "–"}</td>
                    <td className="px-3 text-xs">{a.communication_sent.join(", ") || "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
