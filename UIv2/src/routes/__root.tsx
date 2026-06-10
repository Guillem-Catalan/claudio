import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  createRootRouteWithContext,
  HeadContent,
  Scripts,
  useNavigate,
  useLocation,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { AuthProvider, useAuth } from "@/hooks/use-auth";
import { FloatingBubble } from "@/components/closzr/FloatingBubble";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Claudio — Sales Intelligence" },
      { name: "description", content: "Sales intelligence cockpit for Factorial." },
      { property: "og:title", content: "Claudio — Sales Intelligence" },
      { name: "twitter:title", content: "Claudio — Sales Intelligence" },
      { property: "og:description", content: "Sales intelligence cockpit for Factorial." },
      { name: "twitter:description", content: "Sales intelligence cockpit for Factorial." },
      { property: "og:image", content: "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/d4c98f25-a44e-4d3c-953b-cf622e1d5252/id-preview-c3e006c6--9ee1f5a7-e677-41fd-a577-f74bba6c1af5.lovable.app-1781011101631.png" },
      { name: "twitter:image", content: "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/d4c98f25-a44e-4d3c-953b-cf622e1d5252/id-preview-c3e006c6--9ee1f5a7-e677-41fd-a577-f74bba6c1af5.lovable.app-1781011101631.png" },
      { name: "twitter:card", content: "summary_large_image" },
      { property: "og:type", content: "website" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: () => (
    <div className="min-h-screen flex items-center justify-center text-sm text-gray-500">
      Page not found.
    </div>
  ),
  errorComponent: ({ error }) => (
    <div className="min-h-screen flex items-center justify-center text-sm text-red-600">
      {error.message}
    </div>
  ),
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head><HeadContent /></head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthGate>
          <Outlet />
        </AuthGate>
      </AuthProvider>
    </QueryClientProvider>
  );
}

function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const isEmbed = location.pathname === "/closzr-embed";
  const isAuthRoute = location.pathname === "/auth";

  useEffect(() => {
    if (loading || isEmbed) return;
    if (!user && !isAuthRoute) {
      navigate({ to: "/auth" });
    }
  }, [user, loading, isAuthRoute, isEmbed, navigate]);

  if (loading && !isEmbed) {
    return (
      <div className="min-h-screen flex items-center justify-center text-xs text-gray-400">
        Loading…
      </div>
    );
  }
  if (!isEmbed && !user && !isAuthRoute) return null;
  return (
    <>
      {children}
      {user && !isEmbed && <FloatingBubble />}
    </>
  );
}
