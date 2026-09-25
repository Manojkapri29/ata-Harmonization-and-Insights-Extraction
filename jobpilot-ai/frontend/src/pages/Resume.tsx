import { useState } from "react";
import { Link } from "react-router-dom";
import { Download, Star, Trash2, Upload, Wand2 } from "lucide-react";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";
import type { Resume } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, Empty, ErrorBox, Modal, Notice, PageHeader, ScoreBadge, Skeleton, fmtDate } from "../components/ui";
import { ResumePreview } from "./JobDetail";

export default function ResumePage() {
  const toast = useToast();
  const resumes = useAsync(() => api.resumes());
  const versions = useAsync(() => api.versions());
  const [uploading, setUploading] = useState(false);
  const [drag, setDrag] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [preview, setPreview] = useState<number | null>(null);

  const upload = async (file?: File) => {
    if (!file) return;
    setUploading(true);
    try {
      const r = await api.uploadResume(file);
      toast.success(`Uploaded and parsed ${r.filename}. Job matches were re-scored.`);
      resumes.reload(true);
    } catch (e) { toast.error((e as Error).message); } finally { setUploading(false); }
  };

  const master = resumes.data?.find((r) => r.is_master) ?? resumes.data?.[0];
  const pv = versions.data?.find((v) => v.id === preview);

  return (
    <div className="space-y-6">
      <PageHeader title="Resume" subtitle="Upload your master resume once. Every tailored version is generated from it, without inventing anything." />

      <label onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]); }}
        className={`card flex cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed p-8 text-center transition ${drag ? "border-brand-500 bg-brand-50 dark:bg-brand-600/10" : ""}`}>
        <Upload className="h-8 w-8 text-brand-600" />
        <div className="font-medium">{uploading ? "Uploading and parsing…" : "Drop your master resume here, or click to choose"}</div>
        <div className="text-xs text-slate-500">PDF, DOCX or TXT, up to 5 MB. DOCX gives the most accurate parsing.</div>
        <input type="file" accept=".pdf,.docx,.txt" className="hidden" disabled={uploading} onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
      </label>

      {resumes.error && <ErrorBox message={resumes.error} onRetry={() => resumes.reload()} />}
      {resumes.loading ? <Skeleton /> : !master ? (
        <Card><Empty title="No resume yet" text="Upload your resume to get ATS analysis and tailored versions." /></Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <ParsedView r={master} />
          <div className="space-y-6">
            <Card title="Uploaded resumes" bodyClass="p-2">
              {resumes.data!.map((r) => (
                <div key={r.id} className="flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{r.filename} {r.is_master && <Badge tone="green">Master</Badge>}</div>
                    <div className="text-xs text-slate-500">{fmtDate(r.created_at)} · ATS estimate {r.ats_score ?? "–"}%</div>
                  </div>
                  <div className="flex gap-1">
                    {!r.is_master && <Button variant="ghost" aria-label="Make master" title="Make master" icon={<Star className="h-4 w-4" />} onClick={async () => { await api.setMaster(r.id); resumes.reload(true); toast.success("Master resume changed"); }} />}
                    <Button variant="ghost" aria-label="Delete" icon={<Trash2 className="h-4 w-4" />} onClick={async () => { if (confirm("Delete this resume and its versions?")) { await api.deleteResume(r.id); resumes.reload(true); versions.reload(true); } }} />
                  </div>
                </div>
              ))}
            </Card>
            <Card title="ATS-optimised resume (general)">
              <p className="mb-3 text-sm text-slate-500">Clean single-column layout, standard headings, stronger verbs and organised skills. For a specific job, open it and use <b>Tailor Resume</b>.</p>
              <Button variant="primary" icon={<Wand2 className="h-4 w-4" />} loading={optimizing} onClick={async () => {
                setOptimizing(true);
                try { const v = await api.tailorResume({ resume_id: master.id }); versions.reload(true); setPreview(v.id); toast.success("ATS-optimised version created"); }
                catch (e) { toast.error((e as Error).message); } finally { setOptimizing(false); }
              }}>Create ATS-optimised version</Button>
            </Card>
          </div>
        </div>
      )}

      <Card title="Resume versions" bodyClass="p-0">
        {versions.loading ? <div className="p-4"><Skeleton rows={3} /></div> : !versions.data?.length ? <Empty title="No versions yet" text="Tailored resumes appear here with their job, ATS estimate and version number." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50"><tr>
                <th className="px-4 py-2">File</th><th>Role</th><th>Company</th><th>Version</th><th>ATS est.</th><th>Keywords surfaced</th><th>Created</th><th></th></tr></thead>
              <tbody>
                {versions.data.map((v) => (
                  <tr key={v.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-4 py-2"><button className="text-left font-medium text-brand-600 hover:underline" onClick={() => setPreview(v.id)}>{v.filename_base}</button></td>
                    <td>{v.job_id ? <Link className="hover:underline" to={`/jobs/${v.job_id}?tab=resume`}>{v.role}</Link> : v.role}</td>
                    <td>{v.company || "–"}</td><td>v{v.version}</td><td><ScoreBadge score={v.ats_score} /></td>
                    <td className="max-w-[220px] truncate text-xs">{v.keywords_added.join(", ") || "–"}</td>
                    <td className="whitespace-nowrap">{fmtDate(v.created_at)}</td>
                    <td className="whitespace-nowrap pr-4 text-right">
                      <a className="mr-2 inline-flex items-center gap-1 text-xs text-brand-600" href={api.downloadUrl(v.id, "docx")}><Download className="h-3 w-3" />DOCX</a>
                      <a className="inline-flex items-center gap-1 text-xs text-brand-600" href={api.downloadUrl(v.id, "pdf")}><Download className="h-3 w-3" />PDF</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={!!pv} onClose={() => setPreview(null)} title={pv?.filename_base ?? ""} wide>
        {pv && <>
          <div className="mb-3 flex gap-2">
            <a href={api.downloadUrl(pv.id, "docx")}><Button variant="primary" icon={<Download className="h-4 w-4" />}>DOCX</Button></a>
            <a href={api.downloadUrl(pv.id, "pdf")}><Button icon={<Download className="h-4 w-4" />}>PDF</Button></a>
          </div>
          <ResumePreview r={pv.content} />
          <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-slate-500">{pv.changes.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </>}
      </Modal>
    </div>
  );
}

function ParsedView({ r }: { r: Resume }) {
  const p = r.parsed;
  return (
    <Card title={<span>Parsed master resume <span className="font-normal text-slate-500">· {r.filename}</span></span>}>
      <Notice>Check this carefully: it's what JobPilot "reads". If something is wrong or missing, fix it in your original file and re-upload.</Notice>
      <dl className="mt-4 grid grid-cols-[140px_1fr] gap-x-3 gap-y-1.5 text-sm">
        <dt className="text-slate-500">Name</dt><dd>{p.name || "–"}</dd>
        <dt className="text-slate-500">Contact</dt><dd>{[p.contact?.email, p.contact?.phone, p.contact?.linkedin].filter(Boolean).join(" · ") || "–"}</dd>
        <dt className="text-slate-500">Total experience</dt><dd>{p.total_experience_years != null ? `${p.total_experience_years} years (from dates)` : "Couldn't compute from dates"}</dd>
        <dt className="text-slate-500">Sections found</dt><dd>{p.sections_found?.join(", ")}</dd>
      </dl>
      {p.summary && <><h3 className="mt-4 text-xs font-semibold uppercase text-slate-500">Summary</h3><p className="text-sm">{p.summary}</p></>}
      <h3 className="mt-4 text-xs font-semibold uppercase text-slate-500">Experience</h3>
      {p.experience?.length ? p.experience.map((e: any, i: number) => (
        <div key={i} className="mt-2 text-sm">
          <div className="font-medium">{e.designation || "(title not detected)"} · {e.company || "(company not detected)"} <span className="text-xs font-normal text-slate-500">{e.duration}</span></div>
          <ul className="list-disc pl-5 text-slate-600 dark:text-slate-300">{e.responsibilities.map((b: string) => <li key={b}>{b}{e.achievements.includes(b) && <Badge tone="green" className="ml-1">achievement</Badge>}</li>)}</ul>
        </div>
      )) : <p className="text-sm text-rose-600">No experience entries detected. Use a clear "Experience" heading and date ranges like "Jan 2022 – Present".</p>}
      <h3 className="mt-4 text-xs font-semibold uppercase text-slate-500">Skills</h3>
      <div className="mt-1 flex flex-wrap gap-1">{p.skills?.map((s: string) => <Badge key={s}>{s}</Badge>)}</div>
      <h3 className="mt-4 text-xs font-semibold uppercase text-slate-500">Education</h3>
      {p.education?.map((e: any, i: number) => <p key={i} className="text-sm">{[e.degree, e.institution, e.year, e.score].filter(Boolean).join(" · ")}</p>)}
      {p.certifications?.length > 0 && <><h3 className="mt-4 text-xs font-semibold uppercase text-slate-500">Certifications</h3><ul className="list-disc pl-5 text-sm">{p.certifications.map((c: string) => <li key={c}>{c}</li>)}</ul></>}
      {p.projects?.length > 0 && <><h3 className="mt-4 text-xs font-semibold uppercase text-slate-500">Projects</h3>{p.projects.map((x: any) => <div key={x.name} className="text-sm"><b>{x.name}</b>{x.tech?.length ? ` · ${x.tech.join(", ")}` : ""}</div>)}</>}
    </Card>
  );
}
