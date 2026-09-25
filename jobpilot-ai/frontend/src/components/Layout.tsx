import { Suspense, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  BarChart3, Bell, Briefcase, CalendarClock, FileText, Gauge, LayoutDashboard, Menu, MessageSquare, Moon, Search,
  Settings, Sparkles, Sun, Target, X,
} from "lucide-react";
import { api } from "../lib/api";
import type { Notification } from "../lib/types";
import { useToast } from "./Toast";
import { Button, Spinner, cx } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/search", label: "Job Search", icon: Search },
  { to: "/matches", label: "Job Matches", icon: Target },
  { to: "/resume", label: "Resume", icon: FileText },
  { to: "/ats", label: "ATS Analyzer", icon: Gauge },
  { to: "/applications", label: "Applications", icon: Briefcase },
  { to: "/outreach", label: "HR Outreach", icon: MessageSquare },
  { to: "/followups", label: "Follow-ups", icon: CalendarClock },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try { localStorage.setItem("jobpilot-theme", dark ? "dark" : "light"); } catch { /* storage may be blocked */ }
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

function Bell_() {
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const lastSeen = useRef<number | null>(null);
  const toast = useToast();
  const nav = useNavigate();

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const n = await api.notifications();
        if (!alive) return;
        const maxId = n[0]?.id ?? 0;
        if (lastSeen.current !== null && maxId > lastSeen.current) {
          const fresh = n.filter((x) => x.id > (lastSeen.current ?? 0) && !x.read);
          if (fresh.length) toast.info(`🔥 ${fresh.length} new high-match job${fresh.length > 1 ? "s" : ""}: ${fresh[0].body.role} at ${fresh[0].body.company}`);
        }
        lastSeen.current = maxId;
        setItems(n);
      } catch { /* backend offline; the page itself shows the error */ }
    };
    load();
    const t = window.setInterval(load, 20000);
    return () => { alive = false; window.clearInterval(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const unread = items.filter((i) => !i.read).length;
  const go = async (n: Notification, tab: string) => {
    setOpen(false);
    if (!n.read) { await api.readNotification(n.id).catch(() => {}); setItems((xs) => xs.map((x) => x.id === n.id ? { ...x, read: true } : x)); }
    if (n.job_id) nav(`/jobs/${n.job_id}?tab=${tab}`);
  };

  return (
    <div className="relative">
      <button aria-label={`Notifications (${unread} unread)`} onClick={() => setOpen((o) => !o)}
        className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
        <Bell className="h-5 w-5" />
        {unread > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">{unread}</span>}
      </button>
      {open && (
        <div className="card absolute right-0 z-40 mt-2 max-h-[70vh] w-[min(92vw,400px)] overflow-y-auto p-2">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-sm font-semibold">Job alerts</span>
            {unread > 0 && <button className="text-xs text-brand-600" onClick={async () => { await api.readAll(); setItems((xs) => xs.map((x) => ({ ...x, read: true }))); }}>Mark all read</button>}
          </div>
          {items.length === 0 && <p className="px-2 py-6 text-center text-sm text-slate-500">No alerts yet. High-match jobs from searches appear here.</p>}
          {items.map((n) => (
            <div key={n.id} className={cx("mb-1 rounded-lg p-3 text-sm", n.read ? "opacity-70" : "bg-brand-50 dark:bg-brand-600/10")}>
              <div className="text-xs font-bold text-rose-600">{n.title}</div>
              <div className="mt-1 font-medium">{n.body.role} · {n.body.company}</div>
              <div className="mt-0.5 text-xs text-slate-500">{n.body.location} · Match <b>{n.body.match}%</b> · {n.body.salary}{n.body.posted ? ` · Posted ${n.body.posted}` : ""}</div>
              <div className="mt-2 flex flex-wrap gap-1">
                {[["overview", "Analyze"], ["resume", "Tailor Resume"], ["email", "Generate Email"], ["linkedin", "Generate LinkedIn"], ["track", "Track Application"]].map(([tab, label]) => (
                  <button key={tab} onClick={() => go(n, tab)} className="rounded-md border border-slate-300 px-2 py-0.5 text-xs hover:bg-white dark:border-slate-700 dark:hover:bg-slate-800">{label}</button>
                ))}
                {n.body.application_url && <a href={n.body.application_url} target="_blank" rel="noreferrer" className="rounded-md px-2 py-0.5 text-xs text-brand-600 underline">Open posting</a>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { dark, toggle } = useTheme();
  const [menu, setMenu] = useState(false);
  const [q, setQ] = useState("");
  const nav = useNavigate();

  const sidebar = (
    <nav className="flex h-full flex-col gap-1 p-3">
      <Link to="/" className="mb-4 flex items-center gap-2 px-2 py-1" onClick={() => setMenu(false)}>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white"><Sparkles className="h-4 w-4" /></span>
        <span className="text-base font-bold tracking-tight">JobPilot <span className="text-brand-600">AI</span></span>
      </Link>
      {NAV.map(({ to, label, icon: I, end }) => (
        <NavLink key={to} to={to} end={end} onClick={() => setMenu(false)}
          className={({ isActive }) => cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
            isActive ? "bg-brand-50 text-brand-700 dark:bg-brand-600/15 dark:text-brand-100" : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800")}>
          <I className="h-4 w-4" /> {label}
        </NavLink>
      ))}
      <div className="mt-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-500 dark:bg-slate-800/50">
        Drafts only. JobPilot never applies or sends messages for you.
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-full">
      <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-white lg:sticky lg:top-0 lg:block lg:h-screen lg:overflow-y-auto dark:border-slate-800 dark:bg-slate-900">{sidebar}</aside>
      {menu && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setMenu(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-white dark:bg-slate-900">
            <button className="absolute right-3 top-3" aria-label="Close menu" onClick={() => setMenu(false)}><X className="h-5 w-5" /></button>
            {sidebar}
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-slate-200 bg-white/80 px-4 py-2.5 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
          <button className="rounded-lg p-2 lg:hidden" aria-label="Open menu" onClick={() => setMenu(true)}><Menu className="h-5 w-5" /></button>
          <form className="relative max-w-md flex-1" onSubmit={(e) => { e.preventDefault(); nav(`/matches?q=${encodeURIComponent(q)}`); }}>
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input className="input pl-9" placeholder="Search jobs, companies…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search jobs" />
          </form>
          <div className="ml-auto flex items-center gap-1">
            <Button variant="primary" className="max-sm:hidden" icon={<Search className="h-4 w-4" />} onClick={() => nav("/search?run=1")}>Find Jobs</Button>
            <Bell_ />
            <button aria-label="Toggle dark mode" onClick={toggle} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
              {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6"><Suspense fallback={<Spinner />}><Outlet /></Suspense></main>
      </div>
    </div>
  );
}

