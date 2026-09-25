import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Check, MessageSquarePlus, SkipForward } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import type { Communication, Followup } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, Empty, ErrorBox, Modal, PageHeader, Skeleton, Tabs, fmtDate } from "../components/ui";
import { MessageEditor } from "./JobDetail";

export default function Followups() {
  const toast = useToast();
  const [tab, setTab] = useState<"due" | "upcoming" | "done">("due");
  const list = useAsync(() => api.followups({ status: tab === "done" ? "done,skipped" : "pending", due_only: tab === "due" }), [tab]);
  const [draft, setDraft] = useState<{ fu: Followup; comm: Communication } | null>(null);

  const rows = (list.data ?? []).filter((f) => tab !== "upcoming" || f.due_date > new Date().toISOString().slice(0, 10));
  const act = async (f: Followup, status: "done" | "skipped") => {
    await api.updateFollowup(f.id, { status });
    toast.success(status === "done" ? "Follow-up done" : "Skipped");
    list.reload(true);
  };

  return (
    <div className="space-y-5">
      <PageHeader title="Follow-ups" subtitle="Reminders created when you mark a job as applied: Day 3 LinkedIn/WhatsApp, Day 7 email, Day 14 final (change in Settings)." />
      <Tabs tabs={[{ id: "due", label: "Due now" }, { id: "upcoming", label: "Upcoming" }, { id: "done", label: "Completed" }]} value={tab} onChange={setTab} />
      <Card bodyClass="p-0">
        {list.loading ? <div className="p-4"><Skeleton /></div> : list.error ? <div className="p-4"><ErrorBox message={list.error} /></div> : !rows.length ? (
          <Empty title={tab === "due" ? "Nothing due today" : tab === "upcoming" ? "No upcoming follow-ups" : "No completed follow-ups"}
            text="Follow-ups are scheduled automatically when you mark an application as applied." />
        ) : (
          <ul>
            {rows.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 last:border-0 dark:border-slate-800">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-medium">Day {f.day_offset}: {f.label}</span>
                    {f.overdue && <Badge tone="red"><AlertTriangle className="mr-1 h-3 w-3" />Overdue</Badge>}
                    {f.status !== "pending" && <Badge tone={f.status === "done" ? "green" : "slate"}>{f.status}</Badge>}
                  </div>
                  <div className="text-xs text-slate-500"><Link to={`/jobs/${f.job_id}?tab=track`} className="hover:underline">{f.job_title} · {f.company}</Link> · due {fmtDate(f.due_date)}</div>
                </div>
                {f.status === "pending" && (
                  <div className="flex flex-wrap gap-2">
                    <input type="date" aria-label="Reschedule" className="input w-auto py-1.5" value={f.due_date}
                      onChange={async (e) => { await api.updateFollowup(f.id, { due_date: e.target.value }); list.reload(true); }} />
                    <Button icon={<MessageSquarePlus className="h-4 w-4" />} onClick={async () => setDraft({ fu: f, comm: await api.followupDraft(f.id) })}>Draft message</Button>
                    <Button variant="success" icon={<Check className="h-4 w-4" />} onClick={() => act(f, "done")}>Done</Button>
                    <Button variant="ghost" icon={<SkipForward className="h-4 w-4" />} onClick={() => act(f, "skipped")}>Skip</Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Modal open={!!draft} onClose={() => setDraft(null)} title={draft ? `Follow-up · ${draft.fu.job_title}` : ""} wide>
        {draft && <MessageEditor comm={draft.comm} onSaved={() => { setDraft(null); list.reload(true); }} />}
      </Modal>
    </div>
  );
}
