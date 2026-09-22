import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

interface NavEntry {
  to: string;
  label: string;
  icon: string;
}

function NavItem({ entry, onNavigate }: { entry: NavEntry; onNavigate?: () => void }) {
  return (
    <NavLink
      to={entry.to}
      end={entry.to === "/"}
      onClick={onNavigate}
      className={({ isActive }) =>
        // min-h-11: a 44px target is the smallest thing a thumb hits reliably, and every
        // one of these is meant to be pressed on a phone.
        `flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors ${
          isActive ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
        }`
      }
    >
      <span aria-hidden className="w-5 shrink-0 text-center text-base">
        {entry.icon}
      </span>
      {entry.label}
    </NavLink>
  );
}

/**
 * The application shell.
 *
 * One navigation list, rendered two ways: a permanent rail from `lg` up, and a slide-in
 * drawer below it behind a top bar. Two separate lists would drift — a page added to one
 * and forgotten in the other is invisible to exactly the half of the users who need it
 * most, since on a phone the drawer is the only way anywhere.
 */
export function Layout() {
  const { session, isAdmin, logout } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  const isStaff = session.kind === "employee" && session.employee.is_rtm_staff;
  const isSupervisor = session.kind === "employee" && session.employee.is_supervisor;
  const displayName =
    session.kind === "admin"
      ? session.admin.email
      : session.kind === "employee"
        ? session.employee.full_name
        : "";
  // Which login this session came from. Both identities share one cookie, so naming it out
  // loud answers "why did the admin menu disappear?".
  const via = session.kind === "admin" ? "Admin hisobi" : "HEMIS hisobi";

  const entries: NavEntry[] = [
    { to: "/", label: "Bosh sahifa", icon: "🏠" },
    { to: "/requests", label: "Murojaatlar", icon: "📋" },
    ...(session.kind === "employee"
      ? [
          // Named for what the page actually produces. A Boshliq's form sends a directive
          // — deadline, team, its own card in the group — and calling both "Yangi murojaat"
          // in the sidebar hides the one difference that matters.
          session.employee.can_file_managed_request
            ? { to: "/requests/new", label: "Yangi topshiriq", icon: "👑" }
            : { to: "/requests/new", label: "Yangi murojaat", icon: "➕" },
        ]
      : []),
    { to: "/leaderboard", label: "Top xodimlar", icon: "🏆" },
    { to: "/stats", label: "Statistika", icon: "📊" },
    ...(isStaff || isAdmin
      ? [{ to: "/inventory", label: "RTM Inventar", icon: "📦" }]
      : []),
    { to: "/soft", label: "RTM Soft", icon: "💿" },
    ...(isAdmin
      ? [
          { to: "/employees", label: "Xodimlar", icon: "👥" },
          { to: "/departments", label: "Bo'limlar", icon: "🏢" },
          { to: "/hemis-sync", label: "HEMIS sinxronizatsiya", icon: "🔄" },
          { to: "/admin-notes", label: "Admin uchun eslatmalar", icon: "📌" },
          { to: "/settings", label: "Sozlamalar va kuzatuv", icon: "⚙️" },
        ]
      : []),
  ];

  // Closing on navigation is not a nicety: without it the drawer stays over the page the
  // user just asked for, and the app reads as though the tap did nothing.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    // The page behind a drawer must not scroll — otherwise closing it lands the reader
    // somewhere they never navigated to.
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [drawerOpen]);

  const brand = (
    <div className="px-2">
      <div className="text-lg font-bold text-brand-700">RTM Murojaatlar</div>
      <div className="text-xs text-slate-500">Alfraganus University</div>
    </div>
  );

  const account = (
    <div className="border-t border-slate-200 px-2 pt-4">
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
        className="min-h-11 text-sm text-slate-500 hover:text-red-600"
      >
        Chiqish
      </button>
      {!isAdmin && (
        <p className="mt-1 text-xs text-slate-400">
          Admin panel kerakmi? Avval chiqing, so'ng «Admin sifatida kirish».
        </p>
      )}
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Mobile top bar. Sticky rather than fixed so it does not need a spacer under it. */}
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-slate-200 bg-white px-3 py-2 lg:hidden">
        <button
          onClick={() => setDrawerOpen(true)}
          aria-label="Menyuni ochish"
          aria-expanded={drawerOpen}
          className="flex h-11 w-11 items-center justify-center rounded-lg text-xl text-slate-600 hover:bg-slate-100"
        >
          ☰
        </button>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-bold text-brand-700">RTM Murojaatlar</div>
          <div className="truncate text-[11px] text-slate-500">{displayName}</div>
        </div>
      </header>

      <div className="lg:flex">
        {/* Permanent rail from lg up. */}
        <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white p-4 lg:sticky lg:top-0 lg:block lg:h-screen lg:overflow-y-auto">
          <div className="mb-6">{brand}</div>
          <nav className="space-y-1">
            {entries.map((entry) => (
              <NavItem key={entry.to} entry={entry} />
            ))}
          </nav>
          <div className="mt-8">{account}</div>
        </aside>

        {/* Drawer below lg. Rendered only while open so its links stay out of the tab order. */}
        {drawerOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div
              className="absolute inset-0 bg-slate-900/50"
              onClick={() => setDrawerOpen(false)}
              aria-hidden
            />
            <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col overflow-y-auto bg-white p-4 shadow-xl">
              <div className="mb-6 flex items-start justify-between gap-2">
                {brand}
                <button
                  onClick={() => setDrawerOpen(false)}
                  aria-label="Yopish"
                  className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
                >
                  ✖
                </button>
              </div>
              <nav className="space-y-1">
                {entries.map((entry) => (
                  <NavItem key={entry.to} entry={entry} onNavigate={() => setDrawerOpen(false)} />
                ))}
              </nav>
              <div className="mt-auto pt-8">{account}</div>
            </aside>
          </div>
        )}

        {/* min-w-0 keeps a wide table inside its own scroller instead of stretching the
            page — the flex default of min-width:auto would let it push the layout sideways. */}
        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
