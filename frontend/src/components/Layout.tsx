import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
          isActive ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export function Layout() {
  const { session, isAdmin, logout } = useAuth();
  const isStaff = session.kind === "employee" && session.employee.is_rtm_staff;
  const isSupervisor = session.kind === "employee" && session.employee.is_supervisor;
  const displayName =
    session.kind === "admin" ? session.admin.email : session.kind === "employee" ? session.employee.full_name : "";
  // Which login this session came from. The two share one cookie, so naming it out loud is
  // what answers "why did the admin menu disappear?" — a HEMIS login replaced the panel
  // session, or the other way round.
  const via = session.kind === "admin" ? "Admin hisobi" : "HEMIS hisobi";

  return (
    <div className="flex min-h-screen">
      <aside className="w-64 shrink-0 border-r border-slate-200 bg-white p-4">
        <div className="mb-6 px-2">
          <div className="text-lg font-bold text-brand-700">RTM Murojaatlar</div>
          <div className="text-xs text-slate-500">Alfraganus University</div>
        </div>
        <nav className="space-y-1">
          <NavItem to="/" label="Bosh sahifa" />
          <NavItem to="/requests" label="Murojaatlar" />
          {/* Whether you can *file* a request depends on being an employee, not on
              lacking admin rights — an employee flagged Admin is still a person with a
              broken printer. Only the panel account, which has no employee record, cannot. */}
          {session.kind === "employee" && (
            <NavItem to="/requests/new" label="Yangi murojaat" />
          )}
          <NavItem to="/leaderboard" label="Top xodimlar" />
          <NavItem to="/stats" label="Statistika" />
          {isAdmin && <NavItem to="/employees" label="Xodimlar" />}
          {isAdmin && <NavItem to="/departments" label="Bo'limlar" />}
          {isAdmin && <NavItem to="/hemis-sync" label="HEMIS sinxronizatsiya" />}
        </nav>
        <div className="mt-8 border-t border-slate-200 pt-4 px-2">
          <div className="truncate text-sm text-slate-700">{displayName}</div>
          <div className="mb-2 text-xs text-slate-400">{via}</div>
          <div className="mb-2 flex flex-wrap gap-1">
            {isAdmin && (
              <span className="rounded bg-slate-700 px-2 py-0.5 text-xs text-white">Admin</span>
            )}
            {isSupervisor && (
              <span className="rounded bg-violet-100 px-2 py-0.5 text-xs text-violet-700">
                Boshliq
              </span>
            )}
            {isStaff && (
              <span className="rounded bg-brand-50 px-2 py-0.5 text-xs text-brand-700">
                RTM xodimi
              </span>
            )}
          </div>
          <button
            onClick={() => logout()}
            className="text-sm text-slate-500 hover:text-red-600"
          >
            Chiqish
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto bg-slate-50 p-8">
        <Outlet />
      </main>
    </div>
  );
}
