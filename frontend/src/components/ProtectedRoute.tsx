import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export function ProtectedRoute({ adminOnly = false }: { adminOnly?: boolean }) {
  const { session, loading } = useAuth();

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-400">Yuklanmoqda...</div>;
  }
  if (session.kind === "none") return <Navigate to="/login" replace />;
  if (adminOnly && session.kind !== "admin") return <Navigate to="/" replace />;

  return <Outlet />;
}
