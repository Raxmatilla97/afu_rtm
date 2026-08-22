import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { authApi } from "@/api/auth";
import { ApiError } from "@/api/client";
import type { AdminMe, EmployeeMe } from "@/types";

type Session =
  | { kind: "admin"; admin: AdminMe }
  | { kind: "employee"; employee: EmployeeMe }
  | { kind: "none" };

interface AuthContextValue {
  session: Session;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>({ kind: "none" });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      try {
        const admin = await authApi.adminMe();
        setSession({ kind: "admin", admin });
        return;
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 401) throw e;
      }
      try {
        const employee = await authApi.employeeMe();
        setSession({ kind: "employee", employee });
        return;
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 401) throw e;
      }
      setSession({ kind: "none" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    await authApi.logout();
    setSession({ kind: "none" });
  }, []);

  return (
    <AuthContext.Provider value={{ session, loading, refresh, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
