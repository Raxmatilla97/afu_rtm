import { api } from "@/api/client";

export interface SiteConfig {
  title: string;
  description: string;
  keywords: string;
  organization: string;
  contact_email: string;
  contact_phone: string;
}

export interface SmtpConfig {
  host: string;
  port: number;
  user: string;
  from_address: string;
  starttls: boolean;
  /** The password itself is never sent to the browser — only whether one is stored. */
  has_password: boolean;
}

export interface SmtpUpdate {
  host: string;
  port: number;
  user: string;
  /** Empty means "keep the stored password". */
  password: string;
  from_address: string;
  starttls: boolean;
}

export interface ActivityEvent {
  id: number;
  created_at: string;
  source: string;
  action: string;
  action_label: string;
  actor_name: string;
  employee_id: number | null;
  target: string | null;
  detail: string | null;
}

export interface ActivityDay {
  day: string;
  bot_users: number;
  bot_events: number;
  web_users: number;
  web_events: number;
}

export interface ActorActivity {
  employee_id: number | null;
  actor_name: string;
  last_action: string;
  last_action_label: string;
  last_target: string | null;
  last_source: string;
  last_seen_at: string;
  events: number;
}

export const adminApi = {
  siteSettings: () => api.get<SiteConfig>("/api/admin/settings/site"),
  saveSiteSettings: (config: SiteConfig) =>
    api.post<SiteConfig>("/api/admin/settings/site", config),

  smtpSettings: () => api.get<SmtpConfig>("/api/admin/settings/smtp"),
  saveSmtpSettings: (config: SmtpUpdate) =>
    api.post<SmtpConfig>("/api/admin/settings/smtp", config),
  sendTestEmail: (to_address: string) =>
    api.post<{ message: string }>("/api/admin/settings/smtp/test", { to_address }),

  activity: (opts?: { source?: string; action?: string; q?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.source) params.set("source", opts.source);
    if (opts?.action) params.set("action", opts.action);
    if (opts?.q) params.set("q", opts.q);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return api.get<ActivityEvent[]>(`/api/admin/activity${qs ? `?${qs}` : ""}`);
  },
  activityDaily: (days = 30) =>
    api.get<ActivityDay[]>(`/api/admin/activity/daily?days=${days}`),
  activityActors: (days = 30) =>
    api.get<ActorActivity[]>(`/api/admin/activity/actors?days=${days}`),
};

/** Public — the browser tab's title before anybody has signed in. */
export const publicSiteApi = {
  settings: () =>
    api.get<{ title: string; description: string; organization: string }>("/api/site-settings"),
};
