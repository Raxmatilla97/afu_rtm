import { Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Layout } from "@/components/Layout";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { RequestsListPage } from "@/pages/RequestsListPage";
import { RequestDetailPage } from "@/pages/RequestDetailPage";
import { NewRequestPage } from "@/pages/NewRequestPage";
import { EmployeesPage } from "@/pages/EmployeesPage";
import { DepartmentsPage } from "@/pages/DepartmentsPage";
import { HemisSyncPage } from "@/pages/HemisSyncPage";
import { StatsPage } from "@/pages/StatsPage";
import { LeaderboardPage } from "@/pages/LeaderboardPage";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/requests" element={<RequestsListPage />} />
            <Route path="/requests/new" element={<NewRequestPage />} />
            <Route path="/requests/:id" element={<RequestDetailPage />} />
            <Route path="/leaderboard" element={<LeaderboardPage />} />
            <Route path="/stats" element={<StatsPage />} />

            <Route element={<ProtectedRoute adminOnly />}>
              <Route path="/employees" element={<EmployeesPage />} />
              <Route path="/departments" element={<DepartmentsPage />} />
              <Route path="/hemis-sync" element={<HemisSyncPage />} />
            </Route>
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}
