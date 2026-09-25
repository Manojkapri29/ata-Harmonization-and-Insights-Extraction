import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { JobDetail } from "../lib/types";
import { Button, Card, ErrorBox, Spinner } from "../components/ui";

/** Receives data from the browser bookmarklet (in the URL hash) and imports it. */
export default function ImportPage() {
  const [jobs, setJobs] = useState<JobDetail[] | null>(null);
  const [error, setError] = useState("");
  const once = useRef(false);

  useEffect(() => {
    if (once.current) return;
    once.current = true;
    const hash = window.location.hash.slice(1);
    history.replaceState(null, "", window.location.pathname);   // don't keep page text in history
    if (!hash) { setError("Nothing to import. Use the JobPilot bookmarklet on a job page."); return; }
    let payload: Record<string, unknown>;
    try { payload = JSON.parse(decodeURIComponent(hash)); } catch { setError("The bookmarklet data couldn't be read."); return; }
    api.importPage(payload).then(setJobs).catch((e) => setError((e as Error).message));
  }, []);

  if (error) return <ErrorBox message={error} />;
  if (!jobs) return <Spinner label="Importing job…" />;
  return (
    <Card title="Imported">
      <ul className="space-y-2">
        {jobs.map((j) => (
          <li key={j.id} className="flex items-center justify-between rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div><div className="font-medium">{j.title}</div><div className="text-sm text-slate-500">{j.company} · {j.location} · Match {j.match_score}%</div></div>
            <Link to={`/jobs/${j.id}`}><Button variant="primary">Open</Button></Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
