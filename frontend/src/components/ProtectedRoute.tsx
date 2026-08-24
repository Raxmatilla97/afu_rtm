import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export function ProtectedRoute({ adminOnly = false }: { adminOnly?: boolean }) {
  const { session, isAdmin, loading } = useAuth();

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-400">Yuklanmoqda...</div>;
  }
  if (session.kind === "none") return <Navigate to="/login" replace />;
  // isAdmin, not session.kind: an employee flagged Admin holds the same powers through
  // their own HEMIS login.
  if (adminOnly && !isAdmin) return <Navigate to="/" replace />;

  return <Outlet />;
}
