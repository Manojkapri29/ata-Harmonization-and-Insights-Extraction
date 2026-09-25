export interface Job {
  id: number;
  source: string;
  source_job_id: string;
  job_url: string;
  company: string;
  title: string;
  location: string;
  remote: boolean | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  salary_text: string;
  experience_min: number | null;
  experience_max: number | null;
  employment_type: string;
  posted_date: string | null;
  scraped_at: string;
  created_at: string;
  skills: string[];
  education: string;
  notice_period: string;
  application_url: string;
  hr_name: string;
  hr_email: string;
  company_website: string;
  role_category: string;
  match_score: number | null;
  ats_score: number | null;
  status: string;
  notes: string;
  application_status: string | null;
  application_id: number | null;
}

export interface Match {
  overall: number;
  components: Record<string, { score: number; weight: number }>;
  role_match: number;
  skill_match: number;
  experience_match: number;
  location_match: number;
  salary_match: number;
  education_match: number;
  keyword_match: number;
  matching_skills: string[];
  missing_skills: string[];
  matching_keywords: string[];
  missing_keywords: string[];
  concerns: string[];
  unclear: string[];
  why: string[];
  explanations: Record<string, string>;
  recommendation: string;
  disclaimer: string;
}

export interface JobDetail extends Job {
  description: string;
  match_details: Match | Record<string, never>;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Task {
  id: number;
  kind: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  message: string;
  params: Record<string, unknown>;
  result: Record<string, any> | null;
  error: string;
  created_at: string;
  finished_at: string | null;
}

export interface FormatIssue {
  severity: "high" | "medium" | "low";
  issue: string;
  fix: string;
}

export interface AtsResult {
  ats_score: number;
  label: string;
  disclaimer: string;
  formatting_compatibility: number;
  section_completeness: number;
  readability: number;
  formatting_issues: FormatIssue[];
  section_issues: string[];
  readability_issues: string[];
  parsing_problems: string[];
  parsed_preview: { name: string; contact: Record<string, string>; roles: string[]; skills: string[]; total_experience_years: number | null };
  keyword_coverage?: number;
  skill_coverage?: number;
  relevant_keywords?: string[];
  missing_keywords?: string[];
  skills_present?: string[];
  missing_skills?: string[];
  important_requirements?: string[];
  experience_relevance?: number;
  job_title_relevance?: number;
}

export interface Resume {
  id: number;
  filename: string;
  file_type: string;
  is_master: boolean;
  ats_score: number | null;
  created_at: string;
  parsed: any;
  format_info: Record<string, unknown>;
}

export interface TailoredContent {
  name: string;
  headline: string;
  contact: Record<string, string>;
  summary: string;
  skills_core: string[];
  skills: string[];
  experience: { designation: string; company: string; location: string; duration: string; bullets: string[] }[];
  projects: { name: string; tech: string[]; bullets: string[] }[];
  education: { degree: string; institution: string; year: string; score: string }[];
  certifications: string[];
  ai_used?: boolean;
  ats?: AtsResult;
}

export interface ResumeVersion {
  id: number;
  resume_id: number;
  job_id: number | null;
  kind: string;
  version: number;
  company: string;
  role: string;
  filename_base: string;
  ats_score: number | null;
  keywords_added: string[];
  changes: string[];
  content: TailoredContent;
  created_at: string;
}

export interface Communication {
  id: number;
  job_id: number | null;
  application_id: number | null;
  contact_id: number | null;
  channel: string;
  subject: string;
  body: string;
  status: "draft" | "sent";
  generated_by: string;
  sent_at: string | null;
  created_at: string;
  job_title: string;
  company: string;
}

export interface Application {
  id: number;
  job_id: number;
  status: string;
  applied_date: string | null;
  last_followup_date: string | null;
  next_followup_date: string | null;
  resume_version_id: number | null;
  response_received: boolean;
  communication_sent: string[];
  notes: string;
  created_at: string;
  updated_at: string;
  job_title: string;
  company: string;
  location: string;
  source: string;
  match_score: number | null;
  resume_version_name: string;
}

export interface Followup {
  id: number;
  application_id: number;
  job_id: number | null;
  day_offset: number;
  due_date: string;
  channel: string;
  label: string;
  status: "pending" | "done" | "skipped";
  completed_at: string | null;
  note: string;
  job_title: string;
  company: string;
  overdue: boolean;
}

export interface Contact {
  id: number;
  job_id: number | null;
  company: string;
  name: string;
  role_title: string;
  email: string;
  phone: string;
  linkedin_url: string;
  career_page: string;
  source_note: string;
  notes: string;
  created_at: string;
}

export interface SearchProfile {
  id: number;
  name: string;
  keywords: string[];
  locations: string[];
  experience_min: number | null;
  experience_max: number | null;
  include_remote: boolean;
  min_salary_monthly: number | null;
  posted_within_days: number;
  sources: string[];
  enabled: boolean;
  auto_run: boolean;
  interval_hours: number;
  last_run_at: string | null;
}

export interface Source {
  key: string;
  name: string;
  kind: "api" | "feed" | "company" | "assisted" | "demo";
  description: string;
  requires_credentials: string[];
  missing_credentials: string[];
  config_fields: { name: string; label: string; placeholder: string }[];
  supports_search: boolean;
  default_enabled: boolean;
  terms_note: string;
  enabled: boolean;
  config: Record<string, string>;
  last_run_at: string | null;
  last_status: string;
  last_count: number;
}

export interface Profile {
  id: number;
  full_name: string;
  headline: string;
  email: string;
  phone: string;
  location: string;
  linkedin_url: string;
  summary: string;
  total_experience_years: number | null;
  current_salary_monthly: number | null;
  expected_salary_monthly: number | null;
  notice_period: string;
  education: string[];
  target_roles: string[];
  skills: string[];
  preferred_locations: string[];
  open_to_remote: boolean;
  open_to_relocation_if_relevant: boolean;
}

export interface Notification {
  id: number;
  kind: string;
  title: string;
  body: { company: string; role: string; location: string; match: number; salary: string; posted: string; application_url: string };
  job_id: number | null;
  read: boolean;
  created_at: string;
}

export interface Dashboard {
  jobs_found_today: number;
  jobs_total: number;
  relevant_jobs: number;
  high_match_jobs: number;
  applications: number;
  hr_contacts: number;
  interviews: number;
  offers: number;
  response_rate: number;
  followups_due: number;
  thresholds: { high: number; relevant: number };
}

export interface AssistedLink {
  source: string;
  board: string;
  label: string;
  url: string;
}

export const APP_STATUSES = ["Saved", "Shortlisted", "Resume Tailored", "Applied", "HR Contacted", "Interview",
  "Assessment", "Rejected", "Offer", "Closed"] as const;

export const CHANNEL_LABELS: Record<string, string> = {
  email: "HR Email",
  whatsapp: "WhatsApp",
  linkedin_note: "LinkedIn Note",
  linkedin_dm: "LinkedIn DM",
  cover_letter: "Cover Letter",
  followup_email: "Follow-up Email",
  followup_message: "Follow-up Message",
};
