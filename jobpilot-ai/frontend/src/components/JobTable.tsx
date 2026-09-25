import { Link } from "react-router-dom";
import { ExternalLink, MapPin } from "lucide-react";
import type { Job } from "../lib/types";
import { Badge, ScoreBadge, fmtDate, fmtExp, fmtSalary } from "./ui";

export function JobRow({ job }: { job: Job }) {
  return (
    <Link to={`/jobs/${job.id}`} className="grid grid-cols-[auto_1fr] items-center gap-3 border-b border-slate-100 px-2 py-3 transition last:border-0 hover:bg-slate-50 sm:grid-cols-[64px_1fr_auto] dark:border-slate-800 dark:hover:bg-slate-800/50">
      <div className="text-center"><ScoreBadge score={job.match_score} /></div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-medium text-slate-900 dark:text-white">{job.title}</span>
          {job.source === "demo" && <Badge tone="amber">Sample</Badge>}
          {job.application_status && <Badge tone="violet">{job.application_status}</Badge>}
          {job.remote && <Badge tone="blue">Remote</Badge>}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-500">
          <span className="font-medium text-slate-600 dark:text-slate-300">{job.company || "Unknown company"}</span>
          {job.location && <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" />{job.location}</span>}
          <span>{fmtExp(job)}</span>
          <span>{fmtSalary(job)}</span>
          <span className="capitalize">{job.source}</span>
          <span>Posted {fmtDate(job.posted_date || job.created_at)}</span>
        </div>
      </div>
      <div className="hidden items-center gap-2 sm:flex">
        {job.ats_score != null && <Badge>ATS {job.ats_score}%</Badge>}
        {job.job_url && <ExternalLink className="h-4 w-4 text-slate-400" aria-hidden />}
      </div>
    </Link>
  );
}
