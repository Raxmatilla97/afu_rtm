import { api } from "@/api/client";
import type {
  Category,
  Department,
  Employee,
  HemisSyncRun,
  MonthlyCount,
  StaffRatingSummary,
  StatsSummary,
} from "@/types";

export const departmentsApi = {
  list: () => api.get<Department[]>("/api/departments"),
};

export const employeesApi = {
  list: (opts?: { q?: string; isRtmStaff?: boolean }) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.isRtmStaff !== undefined) params.set("is_rtm_staff", String(opts.isRtmStaff));
    const qs = params.toString();
    return api.get<Employee[]>(`/api/employees${qs ? `?${qs}` : ""}`);
  },
  promote: (id: number) => api.post<Employee>(`/api/employees/${id}/promote-to-staff`),
  demote: (id: number) => api.post<Employee>(`/api/employees/${id}/demote`),
  revoke: (id: number) => api.post<Employee>(`/api/employees/${id}/revoke`),
};

export const categoriesApi = {
  list: () => api.get<Category[]>("/api/categories"),
};

export const hemisSyncApi = {
  run: () => api.post<HemisSyncRun>("/api/hemis-sync/run"),
  last: () => api.get<HemisSyncRun | null>("/api/hemis-sync/last"),
  history: () => api.get<HemisSyncRun[]>("/api/hemis-sync/history"),
};

export const ratingsApi = {
  leaderboard: () => api.get<StaffRatingSummary[]>("/api/ratings/leaderboard"),
};

export const statsApi = {
  summary: () => api.get<StatsSummary>("/api/stats/summary"),
  completedByMonth: () => api.get<MonthlyCount[]>("/api/stats/completed-by-month"),
};
