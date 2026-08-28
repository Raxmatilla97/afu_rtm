import { api } from "@/api/client";
import type { AdminMe, EmployeeMe } from "@/types";

/** What the id-number step tells the form to ask for next. */
export interface QuickLookup {
  status:
    | "needs_password"
    | "needs_setup"
    | "not_found"
    | "not_eligible"
    | "locked";
  full_name: string | null;
  department_name: string | null;
  masked_email: string | null;
  locked_minutes: number;
}

export interface QuickForgotResult {
  sent: boolean;
  masked_email: string | null;
  message: string;
}

export const authApi = {
  adminLogin: (email: string, password: string) =>
    api.post<AdminMe>("/api/auth/login", { email, password }),
  adminMe: () => api.get<AdminMe>("/api/auth/me"),
  employeeMe: () => api.get<EmployeeMe>("/api/auth/employee/me"),
  logout: () => api.post("/api/auth/logout"),

  /**
   * Quick login — the id number on the staff card plus a password set here.
   *
   * The lookup step exists so the form can show whose account is about to be opened
   * before a password is typed: people have been landing in the system under a
   * colleague's name, and this is where that gets caught.
   */
  quickLookup: (employee_id_number: string) =>
    api.post<QuickLookup>("/api/auth/quick/lookup", { employee_id_number }),
  quickLogin: (employee_id_number: string, password: string) =>
    api.post<EmployeeMe>("/api/auth/quick/login", { employee_id_number, password }),
  quickSetup: (employee_id_number: string, password: string, recovery_email: string) =>
    api.post<EmployeeMe>("/api/auth/quick/setup", {
      employee_id_number,
      password,
      recovery_email,
    }),
  quickForgot: (employee_id_number: string) =>
    api.post<QuickForgotResult>("/api/auth/quick/forgot", { employee_id_number }),
  quickReset: (token: string, password: string) =>
    api.post<{ employee_id_number: string; message: string }>("/api/auth/quick/reset", {
      token,
      password,
    }),
};
