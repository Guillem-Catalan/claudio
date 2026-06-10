import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";

export const Route = createFileRoute("/analytics")({
  head: () => ({ meta: [{ title: "Analytics — Claudio" }] }),
  component: () => (
    <AppShell>
      <h2 className="text-base font-semibold text-brand-900">Analytics</h2>
      <p className="mt-2 text-xs text-gray-400">Pending port — siguiente iteración.</p>
    </AppShell>
  ),
});
