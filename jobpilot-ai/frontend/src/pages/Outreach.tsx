import { useState } from "react";
import { Link } from "react-router-dom";
import { Pencil, Trash2, UserPlus } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { CHANNEL_LABELS, type Communication, type Contact } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, Empty, ErrorBox, Modal, Notice, PageHeader, Skeleton, Tabs, fmtDate } from "../components/ui";
import { ContactModal, MessageEditor } from "./JobDetail";

export default function Outreach() {
  const toast = useToast();
  const [tab, setTab] = useState<"messages" | "contacts">("messages");
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const comms = useAsync(() => api.communications({ channel, status }), [channel, status]);
  const contacts = useAsync(() => api.contacts());
  const [open, setOpen] = useState<Communication | null>(null);
  const [editContact, setEditContact] = useState<Contact | null>(null);
  const [newContact, setNewContact] = useState(false);

  return (
    <div className="space-y-5">
      <PageHeader title="HR Outreach" subtitle="Your drafted emails, WhatsApp messages and LinkedIn notes, plus recruiter contacts. You send; JobPilot records." />
      <Notice>Messages are drafts. Send them yourself from your email, WhatsApp or LinkedIn, then click "Mark as sent". Please don't bulk-message recruiters; one personal note per role works better.</Notice>
      <Tabs tabs={[{ id: "messages", label: "Messages" }, { id: "contacts", label: "HR contacts" }]} value={tab} onChange={setTab} />

      {tab === "messages" && (
        <Card bodyClass="p-0">
          <div className="flex flex-wrap gap-2 border-b border-slate-100 p-3 dark:border-slate-800">
            <select className="input max-w-[200px]" aria-label="Channel" value={channel} onChange={(e) => setChannel(e.target.value)}>
              <option value="">All channels</option>{Object.entries(CHANNEL_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select className="input max-w-[160px]" aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Draft & sent</option><option value="draft">Drafts</option><option value="sent">Sent</option>
            </select>
          </div>
          {comms.loading ? <div className="p-4"><Skeleton /></div> : comms.error ? <div className="p-4"><ErrorBox message={comms.error} /></div> : !comms.data?.length ? (
            <Empty title="No messages yet" text="Open a job and generate an email, WhatsApp or LinkedIn message, or run the Application Kit." action={<Link to="/matches"><Button variant="primary">Browse matches</Button></Link>} />
          ) : (
            <ul>
              {comms.data.map((c) => (
                <li key={c.id}>
                  <button onClick={() => setOpen(c)} className="flex w-full items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 text-left last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2 text-sm"><Badge tone="blue">{CHANNEL_LABELS[c.channel] ?? c.channel}</Badge><span className="font-medium">{c.job_title}</span><span className="text-slate-500">· {c.company}</span></div>
                      <div className="mt-1 line-clamp-2 text-xs text-slate-500">{c.subject ? `${c.subject} — ` : ""}{c.body}</div>
                    </div>
                    <div className="shrink-0 text-right text-xs"><Badge tone={c.status === "sent" ? "green" : "slate"}>{c.status}</Badge><div className="mt-1 text-slate-400">{fmtDate(c.created_at)}</div></div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === "contacts" && (
        <Card title="HR contacts" action={<Button icon={<UserPlus className="h-4 w-4" />} onClick={() => setNewContact(true)}>Add contact</Button>} bodyClass="p-0">
          {contacts.loading ? <div className="p-4"><Skeleton /></div> : !contacts.data?.length ? (
            <Empty title="No contacts" text="Add publicly listed recruiters or HR contacts (from the job post, careers page, or their public LinkedIn)." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50"><tr><th className="px-4 py-2">Name</th><th>Company</th><th>Email</th><th>Phone</th><th>LinkedIn</th><th>Source</th><th></th></tr></thead>
                <tbody>{contacts.data.map((c) => (
                  <tr key={c.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-4 py-2"><div className="font-medium">{c.name || "–"}</div><div className="text-xs text-slate-500">{c.role_title}</div></td>
                    <td>{c.job_id ? <Link className="hover:underline" to={`/jobs/${c.job_id}?tab=track`}>{c.company}</Link> : c.company}</td>
                    <td>{c.email ? <a className="text-brand-600" href={`mailto:${c.email}`}>{c.email}</a> : "–"}</td>
                    <td>{c.phone || "–"}</td>
                    <td>{c.linkedin_url ? <a className="text-brand-600" href={c.linkedin_url} target="_blank" rel="noreferrer">Profile</a> : "–"}</td>
                    <td className="text-xs text-slate-500">{c.source_note || "–"}</td>
                    <td className="whitespace-nowrap pr-4 text-right">
                      <Button variant="ghost" aria-label="Edit" icon={<Pencil className="h-4 w-4" />} onClick={() => setEditContact(c)} />
                      <Button variant="ghost" aria-label="Delete" icon={<Trash2 className="h-4 w-4" />} onClick={async () => { if (confirm("Delete contact?")) { await api.deleteContact(c.id); contacts.reload(true); toast.success("Deleted"); } }} />
                    </td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? `${open.job_title} · ${open.company}` : ""} wide>
        {open && <MessageEditor comm={open} onSaved={async () => { await comms.reload(true); setOpen(null); }} />}
      </Modal>
      <ContactModal open={newContact || !!editContact} existing={editContact} onClose={() => { setNewContact(false); setEditContact(null); }}
        onSaved={() => { setNewContact(false); setEditContact(null); contacts.reload(true); }} />
    </div>
  );
}
