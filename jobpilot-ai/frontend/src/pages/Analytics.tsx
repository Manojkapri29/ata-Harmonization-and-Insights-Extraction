import { Download } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { BarViz } from "../components/Charts";
import { Button, Card, ErrorBox, PageHeader, Skeleton, fmtDate } from "../components/ui";

export default function Analytics() {
  const a = useAsync(() => api.analytics());
  if (a.error) return <ErrorBox message={a.error} onRetry={() => a.reload()} />;
  if (a.loading || !a.data) return <Skeleton rows={6} />;
  const d = a.data;
  const totals: [string, number][] = [["Jobs discovered", d.totals.jobs_discovered], ["Shortlisted", d.totals.jobs_shortlisted],
    ["Applications", d.totals.applications], ["HR contacts", d.totals.hr_contacts], ["Responses", d.totals.responses],
    ["Interviews", d.totals.interviews], ["Offers", d.totals.offers]];
  const rates: [string, number, string][] = [["Application rate", d.rates.application_rate, "applications ÷ shortlisted"],
    ["HR response rate", d.rates.hr_response_rate, "responses ÷ applications"],
    ["Interview conversion", d.rates.interview_conversion_rate, "interviews ÷ applications"]];

  return (
    <div className="space-y-6">
      <PageHeader title="Analytics" subtitle={d.note}
        actions={<a href={api.exportUrl("analytics", "xlsx")}><Button icon={<Download className="h-4 w-4" />}>Export</Button></a>} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {totals.map(([l, v]) => <div key={l} className="card p-4"><div className="text-2xl font-semibold">{v}</div><div className="text-xs text-slate-500">{l}</div></div>)}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {rates.map(([l, v, how]) => <div key={l} className="card p-4"><div className="text-2xl font-semibold">{v}%</div><div className="text-sm">{l}</div><div className="text-xs text-slate-500">{how}</div></div>)}
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Applications by week"><BarViz data={d.weekly.map((w: any) => ({ ...w, week: fmtDate(w.week).replace(/ \d{4}$/, "") }))} x="week" y="applications" valueLabel="Applications" /></Card>
        <Card title="Jobs found by week"><BarViz data={d.weekly.map((w: any) => ({ ...w, week: fmtDate(w.week).replace(/ \d{4}$/, "") }))} x="week" y="jobs_found" valueLabel="Jobs found" /></Card>
        <Card title="Application status funnel"><BarViz data={d.funnel} x="stage" y="count" horizontal labels height={280} /></Card>
        <Card title="Match-score distribution"><BarViz data={d.match_distribution} x="range" y="count" labels valueLabel="Jobs" /></Card>
        <Card title="Jobs by source"><BarViz data={d.jobs_by_source} x="name" y="count" horizontal labels valueLabel="Jobs" /></Card>
        <Card title="Jobs by role"><BarViz data={d.jobs_by_role} x="name" y="count" horizontal labels valueLabel="Jobs" /></Card>
        <Card title="Response rate by source"><BarViz data={d.source_response} x="name" y="response_rate" horizontal labels suffix="%" valueLabel="Response rate" /></Card>
        <Card title="Response rate by role"><BarViz data={d.role_response} x="name" y="response_rate" horizontal labels suffix="%" valueLabel="Response rate" /></Card>
      </div>
    </div>
  );
}
