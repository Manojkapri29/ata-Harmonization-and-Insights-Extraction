import type {
  Application, AssistedLink, AtsResult, Communication, Contact, Dashboard, Followup, Job, JobDetail, Match,
  Notification, Paged, Profile, Resume, ResumeVersion, SearchProfile, Source, Task,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Cannot reach the JobPilot backend. Is it running on port 8000?");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? safeJson(text) : undefined;
  if (!res.ok) {
    const detail = (data as any)?.detail;
    const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d: any) => d.msg).join("; ") : `Request failed (${res.status})`;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

function safeJson(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

const get = <T>(p: string) => request<T>("GET", p);
const post = <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const put = <T>(p: string, b: unknown) => request<T>("PUT", p, b);
const patch = <T>(p: string, b: unknown) => request<T>("PATCH", p, b);
const del = (p: string) => request<void>("DELETE", p);

export function qs(params: Record<string, string | number | boolean | undefined | null>) {
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  });
  const out = s.toString();
  return out ? `?${out}` : "";
}

export const api = {
  health: () => get<{ status: string }>("/api/health"),
  dashboard: () => get<Dashboard>("/api/dashboard"),
  analytics: () => get<any>("/api/analytics"),

  jobs: (params: Record<string, string | number | boolean | undefined>) => get<Paged<Job>>(`/api/jobs${qs(params)}`),
  job: (id: number) => get<JobDetail>(`/api/jobs/${id}`),
  createJob: (b: Partial<JobDetail> & { salary_text?: string; experience_text?: string }) => post<JobDetail>("/api/jobs", b),
  updateJob: (id: number, b: Partial<JobDetail>) => patch<JobDetail>(`/api/jobs/${id}`, b),
  deleteJob: (id: number) => del(`/api/jobs/${id}`),
  search: (b: Record<string, unknown>) => post<Task>("/api/jobs/search", b),
  importUrl: (url: string) => post<JobDetail[]>("/api/jobs/import/url", { url }),
  importPage: (b: Record<string, unknown>) => post<JobDetail[]>("/api/jobs/import/page", b),
  analyzeJob: (id: number) => post<any>(`/api/jobs/${id}/analyze`),
  matchJob: (id: number) => post<Match>(`/api/jobs/${id}/match`),
  atsForJob: (id: number) => post<AtsResult>(`/api/jobs/${id}/ats`),
  tailorForJob: (id: number, useAi = true) => post<ResumeVersion>(`/api/jobs/${id}/resume?use_ai=${useAi}`),
  jobVersions: (id: number) => get<ResumeVersion[]>(`/api/jobs/${id}/resume`),
  jobComms: (id: number) => get<Communication[]>(`/api/jobs/${id}/communications`),
  generateComms: (id: number, channels: string[], contact_id?: number) =>
    post<Communication[]>(`/api/jobs/${id}/communications`, { channels, contact_id }),
  kit: (id: number) => post<Task>(`/api/jobs/${id}/kit`),
  getKit: (id: number) => get<any>(`/api/jobs/${id}/kit`),
  apply: (id: number, b: { resume_version_id?: number | null; applied_on?: string } = {}) => post<any>(`/api/jobs/${id}/apply`, b),
  rescore: () => post<{ rescored: number }>("/api/jobs/rescore"),

  resumes: () => get<Resume[]>("/api/resumes"),
  uploadResume: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return post<Resume>("/api/resumes?make_master=true", fd);
  },
  setMaster: (id: number) => post<Resume>(`/api/resumes/${id}/master`),
  deleteResume: (id: number) => del(`/api/resumes/${id}`),
  analyzeResume: (b: { resume_id?: number; job_id?: number; jd_text?: string; job_title?: string }) => post<AtsResult>("/api/resumes/analyze", b),
  tailorResume: (b: { resume_id?: number; job_id?: number | null; use_ai?: boolean }) => post<ResumeVersion>("/api/resumes/tailor", b),
  versions: (jobId?: number) => get<ResumeVersion[]>(`/api/resumes/versions${qs({ job_id: jobId })}`),
  version: (id: number) => get<ResumeVersion>(`/api/resumes/versions/${id}`),
  deleteVersion: (id: number) => del(`/api/resumes/versions/${id}`),
  downloadUrl: (id: number, format: "docx" | "pdf") => `/api/resumes/versions/${id}/download?format=${format}`,

  applications: (params: Record<string, string> = {}) => get<Application[]>(`/api/applications${qs(params)}`),
  application: (id: number) => get<{ application: Application; followups: Followup[]; communications: Communication[] }>(`/api/applications/${id}`),
  createApplication: (b: { job_id: number; status?: string }) => post<Application>("/api/applications", b),
  updateApplication: (id: number, b: Partial<Application>) => patch<Application>(`/api/applications/${id}`, b),
  deleteApplication: (id: number) => del(`/api/applications/${id}`),

  contacts: (params: Record<string, string | number> = {}) => get<Contact[]>(`/api/contacts${qs(params)}`),
  createContact: (b: Partial<Contact>) => post<Contact>("/api/contacts", b),
  updateContact: (id: number, b: Partial<Contact>) => patch<Contact>(`/api/contacts/${id}`, b),
  deleteContact: (id: number) => del(`/api/contacts/${id}`),

  communications: (params: Record<string, string> = {}) => get<Communication[]>(`/api/communications${qs(params)}`),
  updateCommunication: (id: number, b: { subject?: string; body?: string; mark_sent?: boolean; confirm?: boolean }) =>
    patch<Communication>(`/api/communications/${id}`, b),
  commLinks: (id: number) => get<{ mailto: string; whatsapp: string; linkedin: string }>(`/api/communications/${id}/links`),
  deleteCommunication: (id: number) => del(`/api/communications/${id}`),

  followups: (params: Record<string, string | boolean> = {}) => get<Followup[]>(`/api/followups${qs(params)}`),
  updateFollowup: (id: number, b: Partial<Followup>) => patch<Followup>(`/api/followups/${id}`, b),
  followupDraft: (id: number) => post<Communication>(`/api/followups/${id}/draft`),

  profile: () => get<Profile>("/api/profile"),
  saveProfile: (b: Omit<Profile, "id">) => put<Profile>("/api/profile", b),
  settings: () => get<any>("/api/settings"),
  saveSettings: (b: Record<string, unknown>) => put<any>("/api/settings", b),
  testAi: () => post<{ ok: boolean; provider: string; message: string }>("/api/settings/ai/test"),
  sources: () => get<Source[]>("/api/sources"),
  updateSource: (key: string, b: { enabled?: boolean; config?: Record<string, string> }) => patch<any>(`/api/sources/${key}`, b),
  assistedLinks: (spId?: number) => get<AssistedLink[]>(`/api/sources/links${qs({ search_profile_id: spId })}`),

  searchProfiles: () => get<SearchProfile[]>("/api/search-profiles"),
  createSearchProfile: (b: Omit<SearchProfile, "id" | "last_run_at">) => post<SearchProfile>("/api/search-profiles", b),
  updateSearchProfile: (id: number, b: Omit<SearchProfile, "id" | "last_run_at">) => put<SearchProfile>(`/api/search-profiles/${id}`, b),
  deleteSearchProfile: (id: number) => del(`/api/search-profiles/${id}`),
  runSearchProfile: (id: number) => post<Task>(`/api/search-profiles/${id}/run`),

  task: (id: number) => get<Task>(`/api/tasks/${id}`),
  tasks: () => get<Task[]>("/api/tasks"),
  notifications: () => get<Notification[]>("/api/notifications"),
  readNotification: (id: number) => post<void>(`/api/notifications/${id}/read`),
  readAll: () => post<void>("/api/notifications/read-all"),

  exportUrl: (entity: string, format: string) => `/api/export/${entity}?format=${format}`,
  importJobs: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return post<{ imported: number; updated: number; skipped: number }>("/api/import/jobs", fd);
  },
};
