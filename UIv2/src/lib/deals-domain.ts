// Domain helpers ported verbatim from the original single-page app.
// Source: pasted-2026-06-05*.txt (Claudio — Sales Intelligence).
// Keep these pure / framework-agnostic; UI imports them as needed.

export type Deal = {
  id: string | number;
  deal_name?: string | null;
  deal_stage?: string | null;
  amount?: number | null;
  close_date?: string | null;
  last_contacted_hs?: string | null;
  pae?: string | null;
  pbd?: string | null;
  probability?: number | null;
  [k: string]: unknown;
};

export type Snapshot = {
  deal_id: string | number;
  action_signal?: string | null;
  live_blockers?: string | null;
  next_step?: string | null;
  buyer_signals?: string | null;
  [k: string]: unknown;
};

export const PIPELINE_PHASES = [
  { key: "prospecting", label: "Prospecting", staleDays: 21 },
  { key: "qualifying", label: "Qualifying", staleDays: 14 },
  { key: "demo", label: "Demo", staleDays: 10 },
  { key: "evaluating", label: "Evaluating", staleDays: 14 },
  { key: "closing", label: "Closing", staleDays: 7 },
  { key: "nurturing", label: "Nurturing", staleDays: 30 },
  { key: "onhold", label: "On hold", staleDays: 45 },
  { key: "other", label: "Other", staleDays: 14 },
] as const;

export type PhaseKey = (typeof PIPELINE_PHASES)[number]["key"];

// Stage → phase mapping. Extend as we confirm real stage strings from the DB.
export const STAGE_TO_PHASE: Record<string, PhaseKey> = {
  "Prospecting": "prospecting",
  "Qualifying": "qualifying",
  "Demo Scheduled": "demo",
  "Demo Done": "demo",
  "Evaluating": "evaluating",
  "Proposal Sent": "evaluating",
  "Negotiation": "closing",
  "Closing": "closing",
  "Nurturing": "nurturing",
  "On Hold": "onhold",
};

export const EXCLUDE_STAGES = new Set([
  "Opportunity lost", "Closed lost", "Closed Lost", "Closed won", "Closed Won",
  "Closed Won - Finance Only", "Opportunity Lost", "Opportunity Lost ",
  "Onboarding Completed - Converted", "Onboarding Completed - Pending Conversion",
  "Onboarding Failed", "Onboarding On Hold",
  "> 75% sessions done", "51-75% sessions done", "26-50% sessions done",
  "≤ 25% sessions done", "1st Session Scheduled", "Client pending to launch",
  "Churned (Closed)", "Retained (Closed)", "Preventive Churn Risk (New)",
  "Requested Churn (New)", "(DO NOT USE) Churn Confirmed",
  "Product related process (Ongoing)", "Pending approval because low joined rate",
  "Wrongly Created Ticket (Closed)", "SPAM",
  "(DO NOT USE) Pending Post-Mortem Analysis", "(DO NOT USE) Action Plan",
  "Closed - pending finance validation",
]);

export function daysSinceContact(deal: Deal): number {
  if (!deal.last_contacted_hs) return Infinity;
  return Math.floor(
    (Date.now() - new Date(deal.last_contacted_hs).getTime()) / 86_400_000,
  );
}

export function isStale(deal: Deal): boolean {
  const phaseKey = STAGE_TO_PHASE[deal.deal_stage ?? ""] ?? "other";
  const phase = PIPELINE_PHASES.find((p) => p.key === phaseKey);
  const threshold = phase?.staleDays ?? 14;
  return daysSinceContact(deal) > threshold;
}

export function pipelineSignal(
  deal: Deal,
  snap?: Snapshot,
): { text: string; cls: string } {
  const days = daysSinceContact(deal);
  if (isStale(deal)) {
    return {
      text: `Sin contacto hace ${days === Infinity ? "?" : days} d`,
      cls: "text-red-600 font-medium",
    };
  }
  if (snap?.action_signal) {
    const sig = snap.action_signal.trim();
    if (sig) return { text: sig.length > 60 ? sig.slice(0, 57) + "…" : sig, cls: "text-brand-700 font-medium" };
  }
  if (snap?.live_blockers) {
    const first = snap.live_blockers.split("\n")[0].replace(/^[-•!*\s]+/, "").trim();
    if (first) return { text: "Blocker: " + (first.length > 50 ? first.slice(0, 47) + "…" : first), cls: "text-amber-700" };
  }
  if (snap?.next_step) {
    const first = snap.next_step.split("\n")[0].replace(/^[-•]\s*/, "").trim();
    if (first) return { text: first.length > 55 ? first.slice(0, 52) + "…" : first, cls: "text-gray-600" };
  }
  if (snap?.buyer_signals) {
    const first = snap.buyer_signals.split("\n")[0].replace(/^[-•+]\s*/, "").trim();
    if (first) return { text: first.length > 55 ? first.slice(0, 52) + "…" : first, cls: "text-green-600" };
  }
  const phaseKey = STAGE_TO_PHASE[deal.deal_stage ?? ""] ?? "other";
  const defaults: Record<string, string> = {
    closing: "En negociación final",
    evaluating: "En evaluación",
    demo: "Demo pendiente",
    nurturing: "En seguimiento",
    qualifying: "Contacto inicial",
    prospecting: "Pendiente de primer contacto",
    onhold: "Deal pausado",
  };
  return { text: defaults[phaseKey] ?? "—", cls: "text-gray-400 italic" };
}

export function formatMRR(amount?: number | null): string {
  if (amount == null) return "—";
  if (amount >= 1000) return `${(amount / 1000).toFixed(1)}k€`;
  return `${Math.round(amount)}€`;
}

export function probColor(p?: number | null): string {
  if (p == null) return "bg-gray-100 text-gray-600";
  if (p >= 70) return "bg-green-100 text-green-700";
  if (p >= 40) return "bg-amber-100 text-amber-700";
  return "bg-red-100 text-red-700";
}
