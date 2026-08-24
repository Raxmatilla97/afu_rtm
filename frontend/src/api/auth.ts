import { api } from "@/api/client";
import type { AdminMe, EmployeeMe } from "@/types";

export const authApi = {
  adminLogin: (email: string, password: string) =>
    api.post<AdminMe>("/api/auth/login", { email, password }),
  adminMe: () => api.get<AdminMe>("/api/auth/me"),
  employeeMe: () => api.get<EmployeeMe>("/api/auth/employee/me"),
  logout: () => api.post("/api/auth/logout"),
};
