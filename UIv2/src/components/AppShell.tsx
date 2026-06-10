import { Link, useLocation } from "@tanstack/react-router";
import { useAuth } from "@/hooks/use-auth";

const TABS = [
  { to: "/", label: "General" },
  { to: "/forecast", label: "Forecast" },
  { to: "/deals", label: "Deals" },
  { to: "/analytics", label: "Analytics" },
  { to: "/oneone", label: "1:1" },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, signOut } = useAuth();
  const location = useLocation();

  return (
    <div className="min-h-screen bg-[#f8fafc]">
      <nav className="bg-white border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-6 flex items-center gap-6 h-14">
          <Link to="/" className="font-bold text-brand-800 text-base">Claudio</Link>
          <div className="flex items-center gap-1 flex-1">
            {TABS.map((t) => {
              const active = location.pathname === t.to;
              return (
                <Link
                  key={t.to}
                  to={t.to}
                  className={`px-4 py-3 text-sm transition-colors ${
                    active ? "tab-active" : "text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {t.label}
                </Link>
              );
            })}
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="truncate max-w-[200px]">{user?.email}</span>
            <button
              onClick={() => signOut()}
              className="px-3 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50"
            >
              Sign out
            </button>
          </div>
        </div>
      </nav>
      <main className="max-w-[1600px] mx-auto px-6 py-6 fade-in">{children}</main>
    </div>
  );
}
