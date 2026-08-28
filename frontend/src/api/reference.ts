import { api } from "@/api/client";
import type {
  Category,
  Department,
  Employee,
  HemisSyncRun,
  MonthlyCount,
  StaffRatingSummary,
  StatsOverview,
  StatsSummary,
} from "@/types";

export const departmentsApi = {
  list: () => api.get<Department[]>("/api/departments"),
};

export const employeesApi = {
  list: (opts?: {
    q?: string;
    isRtmStaff?: boolean;
    departmentId?: number;
    /** "name" (default) or "requests" — most requests filed first. */
    sort?: "name" | "requests";
  }) => {
    const params = new URLSearchParams();
    if (opts?.q) params.set("q", opts.q);
    if (opts?.isRtmStaff !== undefined) params.set("is_rtm_staff", String(opts.isRtmStaff));
    if (opts?.departmentId !== undefined) params.set("department_id", String(opts.departmentId));
    if (opts?.sort) params.set("sort", opts.sort);
    const qs = params.toString();
    return api.get<Employee[]>(`/api/employees${qs ? `?${qs}` : ""}`);
  },
  /**
   * Just the RTM staff, readable by Boshliq as well as Admin.
   *
   * `list()` above is admin-only, so a Boshliq calling it got a 403 and an empty assign
   * form. Anything that only needs "who can take this job" should use this.
   */
  rtmStaff: () => api.get<Employee[]>("/api/employees/rtm-staff"),
  promote: (id: number) => api.post<Employee>(`/api/employees/${id}/promote-to-staff`),
  demote: (id: number) => api.post<Employee>(`/api/employees/${id}/demote`),
  revoke: (id: number) => api.post<Employee>(`/api/employees/${id}/revoke`),
  /** Partial update — only the flags passed are changed. */
  setRoles: (
    id: number,
    roles: Partial<{
      is_rtm_staff: boolean;
      is_supervisor: boolean;
      is_admin: boolean;
      is_blocked: boolean;
    }>,
  ) => api.post<Employee>(`/api/employees/${id}/roles`, roles),
  /**
   * Correct an employee's record by hand. Only the keys passed are written — a field left
   * out is untouched, and one explicitly set to null is cleared.
   */
  update: (
    id: number,
    fields: Partial<{
      full_name: string;
      department_id: number | null;
      phone_number: string | null;
      telegram_username: string | null;
      recovery_email: string | null;
      hemis_email: string | null;
      hemis_phone: string | null;
      year_of_enter: number | null;
    }>,
  ) => api.post<Employee>(`/api/employees/${id}/profile`, fields),
  uploadPhoto: (id: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.postForm<Employee>(`/api/employees/${id}/photo`, form);
  },
  /** Drops the current portrait. HEMIS refills it on the next sync if it has one. */
  deletePhoto: (id: number) => api.post<Employee>(`/api/employees/${id}/photo/delete`),
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
  overview: () => api.get<StatsOverview>("/api/stats/overview"),
};
