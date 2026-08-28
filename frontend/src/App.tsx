import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { publicSiteApi } from "@/api/admin";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Layout } from "@/components/Layout";
import { LoginPage } from "@/pages/LoginPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { RequestsListPage } from "@/pages/RequestsListPage";
import { RequestDetailPage } from "@/pages/RequestDetailPage";
import { NewRequestPage } from "@/pages/NewRequestPage";
import { EmployeesPage } from "@/pages/EmployeesPage";
import { InventoryPage } from "@/pages/InventoryPage";
import { SoftPage } from "@/pages/SoftPage";
import { DepartmentsPage } from "@/pages/DepartmentsPage";
import { HemisSyncPage } from "@/pages/HemisSyncPage";
import { StatsPage } from "@/pages/StatsPage";
import { LeaderboardPage } from "@/pages/LeaderboardPage";
import { AdminNotesPage } from "@/pages/AdminNotesPage";
import { SettingsPage } from "@/pages/SettingsPage";

export default function App() {
  // The tab title and the meta description are editable in the admin panel, and this is
  // a single-page app: index.html is served once and never rebuilt per install. Applying
  // them here is what makes the setting real without a deploy. Failure is silent on
  // purpose — a title that did not load is not worth an error screen over.
  useEffect(() => {
    publicSiteApi
      .settings()
      .then((site) => {
        document.title = site.title;
        let meta = document.querySelector('meta[name="description"]');
        if (!meta) {
          meta = document.createElement("meta");
          meta.setAttribute("name", "description");
          document.head.appendChild(meta);
        }
        meta.setAttribute("content", site.description);
      })
      .catch(() => undefined);
  }, []);

  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        {/* Public: the link in a password reset email lands here, and whoever follows it
            is by definition unable to sign in. */}
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/requests" element={<RequestsListPage />} />
            <Route path="/requests/new" element={<NewRequestPage />} />
            <Route path="/requests/:id" element={<RequestDetailPage />} />
            <Route path="/leaderboard" element={<LeaderboardPage />} />
            <Route path="/stats" element={<StatsPage />} />
            <Route path="/inventory" element={<InventoryPage />} />
            <Route path="/soft" element={<SoftPage />} />

            <Route element={<ProtectedRoute adminOnly />}>
              <Route path="/employees" element={<EmployeesPage />} />
              <Route path="/departments" element={<DepartmentsPage />} />
              <Route path="/hemis-sync" element={<HemisSyncPage />} />
              <Route path="/admin-notes" element={<AdminNotesPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
