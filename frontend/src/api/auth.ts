import { api } from "@/api/client";
import type { AdminMe, EmployeeMe } from "@/types";

export const authApi = {
  adminLogin: (email: string, password: string) =>
    api.post<AdminMe>("/api/auth/login", { email, password }),
  adminMe: () => api.get<AdminMe>("/api/auth/me"),
  employeeMe: () => api.get<EmployeeMe>("/api/auth/employee/me"),
  logout: () => api.post("/api/auth/logout"),
  telegramLinkStart: (employee_id_number: string) =>
    api.post<{ token: string; deep_link: string; expires_at: string }>("/api/auth/telegram-link/start", {
      employee_id_number,
    }),
  telegramLinkStatus: (token: string) =>
    api.get<{ status: string; session_ready: boolean }>(`/api/auth/telegram-link/${token}`),
};
