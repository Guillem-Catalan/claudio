import { createFileRoute } from "@tanstack/react-router";
import { useEffect } from "react";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [{ title: "Claudio — Sales Intelligence" }] }),
  component: LegacyRedirect,
});

function LegacyRedirect() {
  useEffect(() => {
    // Full reload into the legacy HTML app (served from /public).
    // Keep a versioned URL so preview/browser cache cannot serve stale legacy.html.
    window.location.replace("/legacy.html?v=meddic-accumulate-20260610");
  }, []);
  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-gray-500">
      Cargando Claudio…
    </div>
  );
}
