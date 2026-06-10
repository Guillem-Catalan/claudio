import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AppShell } from "@/components/AppShell";
import { supabase } from "@/integrations/supabase/client";
import { EXCLUDE_STAGES } from "@/lib/deals-domain";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export const Route = createFileRoute("/forecast")({
  head: () => ({ meta: [{ title: "Forecast — Claudio" }] }),
  component: ForecastPage,
});

// ---------- types ----------
type DashRow = {
  deal_id: string;
  hs_deal_id?: string | null;
  deal_name: string | null;
  amount: number | null;
  deal_stage: string | null;
  pae: string | null;
  pbd: string | null;
  close_date: string | null;
  forecast_category: string | null;
  close_probability: number | null;
  live_blockers: string | null;
  objections: string | null;
  snapshot_date: string | null;
  claudio_close_date: string | null;
};

type TargetRow = { team: string; month: string; monthly_target: number };

type ClosedRow = {
  deal_name: string | null;
  amount: number | null;
  close_date: string | null;
  pae: string | null;
  pbd: string | null;
};

type SnapshotRow = {
  deal_id: string;
  snapshot_date: string;
  amount: number | null;
  forecast_category: string | null;
  close_probability: number | null;
  close_date: string | null;
};

// ---------- helpers ----------
const FORECAST_CATEGORIES = new Set(["Commit", "Upside", "Pipeline_new"]);
const CLAUDIO_FORECAST_CATS = new Set(["Commit", "Upside"]);
const CLOSED_WON_STAGES = ["Closed Won", "Closed won", "Closed Won - Finance Only"];

const TEAM_NORMALIZED: Record<string, string> = {
  Santander: "Santander",
  Telefónica: "Telefónica",
  TIM: "TIM",
  "Deutsche Telekom": "TELEKOM",
  TELEKOM: "TELEKOM",
};

function extractTeam(dealName?: string | null): string {
  if (!dealName) return "";
  const m = dealName.match(
    /(Santander|Telefónica|Telefonica|TIM|TELEKOM|Deutsche\s+Telekom)/i,
  );
  if (!m) return "";
  const raw = m[1].toLowerCase();
  if (raw.includes("telefonica") || raw.includes("telefónica")) return "Telefónica";
  if (raw.includes("telekom")) return "TELEKOM";
  if (raw.includes("santander")) return "Santander";
  if (raw === "tim") return "TIM";
  return "";
}

function formatAmount(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return "€" + Math.round(n).toLocaleString("de-DE");
}

function monthKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function quarterKey(d: Date): string {
  const q = Math.floor(d.getMonth() / 3) + 1;
  return `${d.getFullYear()}-Q${q}`;
}

function periodOfDate(dateStr: string | null, period: "month" | "quarter"): string | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return null;
  return period === "month" ? monthKey(d) : quarterKey(d);
}

function currentMonthKey(): string {
  return monthKey(new Date());
}

function lastNPeriods(period: "month" | "quarter", n: number): string[] {
  const out: string[] = [];
  const now = new Date();
  if (period === "month") {
    for (let i = n - 1; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      out.push(monthKey(d));
    }
  } else {
    for (let i = n - 1; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i * 3, 1);
      out.push(quarterKey(d));
    }
  }
  return Array.from(new Set(out));
}

function countWarnings(blockers: string | null, objections: string | null): number {
  let c = 0;
  for (const t of [blockers, objections]) {
    if (!t) continue;
    c += t.split(/[\n•\-*]/).filter((s) => s.trim().length > 3).length;
  }
  return c;
}

async function fetchAllPaged<T>(
  table: string,
  cols: string,
  filter?: (q: any) => any,
): Promise<T[]> {
  const all: T[] = [];
  let offset = 0;
  const PAGE = 1000;
  while (true) {
    let q: any = supabase.from(table).select(cols);
    if (filter) q = filter(q);
    q = q.range(offset, offset + PAGE - 1);
    const { data, error } = await q;
    if (error) throw error;
    const rows = (data ?? []) as T[];
    all.push(...rows);
    if (rows.length < PAGE) break;
    offset += PAGE;
  }
  return all;
}

// ---------- component ----------
function ForecastPage() {
  const [rows, setRows] = useState<DashRow[]>([]);
  const [targets, setTargets] = useState<TargetRow[]>([]);
  const [closed, setClosed] = useState<ClosedRow[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [teamFilter, setTeamFilter] = useState<string>("");
  const [paeFilter, setPaeFilter] = useState<string>("");
  const [period, setPeriod] = useState<"month" | "quarter">("month");
  const [showChart, setShowChart] = useState(true);
  const [warningsFor, setWarningsFor] = useState<DashRow | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const errs: string[] = [];
      const safe = async <T,>(label: string, fn: () => Promise<T>, fallback: T): Promise<T> => {
        try {
          return await fn();
        } catch (e) {
          const msg =
            e instanceof Error
              ? e.message
              : typeof e === "object" && e
                ? ((e as { message?: string }).message ?? JSON.stringify(e))
                : String(e);
          console.error(`[forecast] ${label} failed:`, e);
          errs.push(`${label}: ${msg}`);
          return fallback;
        }
      };

      const cm = currentMonthKey();
      const [dash, tgt, won, snaps] = await Promise.all([
        safe<DashRow[]>(
          "v_deals_dashboard",
          () =>
            fetchAllPaged<DashRow>(
              "v_deals_dashboard",
              "deal_id,hs_deal_id,deal_name,amount,deal_stage,pae,pbd,close_date,forecast_category,close_probability,live_blockers,objections,snapshot_date,claudio_close_date",
            ),
          [],
        ),
        safe<TargetRow[]>(
          "forecast_targets",
          async () => {
            const r = await supabase
              .from("forecast_targets")
              .select("team,month,monthly_target")
              .eq("month", cm);
            if (r.error) throw r.error;
            return (r.data ?? []) as TargetRow[];
          },
          [],
        ),
        safe<ClosedRow[]>(
          "deals (closed won)",
          () =>
            fetchAllPaged<ClosedRow>(
              "deals",
              "deal_name,amount,close_date,pae,pbd,deal_stage",
              (q) => q.in("deal_stage", CLOSED_WON_STAGES),
            ),
          [],
        ),
        safe<SnapshotRow[]>(
          "front_deal_snapshots",
          () =>
            fetchAllPaged<SnapshotRow>(
              "front_deal_snapshots",
              "deal_id,snapshot_date,amount,forecast_category,close_probability,close_date",
            ),
          [],
        ),
      ]);
      if (!alive) return;
      setRows(dash.filter((d) => !EXCLUDE_STAGES.has(d.deal_stage ?? "")));
      setTargets(tgt);
      setClosed(won);
      setSnapshots(snaps);
      if (errs.length) setErr(errs.join(" | "));
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  // PAE options across teams (filtered if team selected)
  const paeOptions = useMemo(() => {
    const set = new Set<string>();
    for (const d of rows) {
      if (teamFilter && extractTeam(d.deal_name) !== teamFilter) continue;
      const p = d.pae || d.pbd;
      if (p) set.add(p);
    }
    return Array.from(set).sort();
  }, [rows, teamFilter]);

  // Filtered deals for forecast (active deals in commit/upside/pipeline_new)
  const forecastDeals = useMemo(() => {
    return rows.filter((d) => {
      const fc = d.forecast_category || "";
      if (!FORECAST_CATEGORIES.has(fc)) return false;
      if (teamFilter && extractTeam(d.deal_name) !== teamFilter) return false;
      if (paeFilter && d.pae !== paeFilter && d.pbd !== paeFilter) return false;
      return true;
    });
  }, [rows, teamFilter, paeFilter]);

  // Cards
  const target = useMemo(() => {
    if (!teamFilter) {
      return targets.reduce((s, t) => s + Number(t.monthly_target || 0), 0);
    }
    // map UI team label -> normalized in targets table
    const key = TEAM_NORMALIZED[teamFilter] ?? teamFilter;
    const match = targets.find(
      (t) => t.team === key || t.team === teamFilter,
    );
    return match ? Number(match.monthly_target) : 0;
  }, [targets, teamFilter]);

  const teamForecast = useMemo(() => {
    return forecastDeals
      .filter((d) => d.forecast_category === "Commit" || d.forecast_category === "Upside")
      .reduce((s, d) => s + Number(d.amount || 0), 0);
  }, [forecastDeals]);

  const claudioForecast = useMemo(() => {
    return forecastDeals
      .filter((d) => CLAUDIO_FORECAST_CATS.has(d.forecast_category ?? ""))
      .reduce((s, d) => {
        const p = d.close_probability ?? 50;
        return s + (Number(d.amount || 0) * p) / 100;
      }, 0);
  }, [forecastDeals]);

  const actualClosedThisMonth = useMemo(() => {
    const cm = currentMonthKey();
    return closed
      .filter((c) => {
        if (teamFilter && extractTeam(c.deal_name) !== teamFilter) return false;
        if (paeFilter && c.pae !== paeFilter && c.pbd !== paeFilter) return false;
        return periodOfDate(c.close_date, "month") === cm;
      })
      .reduce((s, c) => s + Number(c.amount || 0), 0);
  }, [closed, teamFilter, paeFilter]);

  // Chart data: latest snapshot per (deal, period) for team/claudio forecasts,
  // plus actual closed (deals table). Bucketed by period.
  const chartData = useMemo(() => {
    const periods = lastNPeriods(period, period === "month" ? 6 : 4);

    // Bucket snapshots: pick latest snapshot per deal within each period
    type Bucket = { team: number; claudio: number };
    const buckets = new Map<string, Bucket>();
    for (const p of periods) buckets.set(p, { team: 0, claudio: 0 });

    // Group snapshots by deal+period (close_date determines bucket; latest snapshot_date wins)
    const latestPerKey = new Map<
      string,
      { snapshot_date: string; amount: number; fc: string; prob: number | null }
    >();
    for (const s of snapshots) {
      if (teamFilter && extractTeam((s as unknown as { deal_name?: string }).deal_name) !== teamFilter) {
        // deal_name not selected; skip team filter at snapshot level
      }
      const bucket = periodOfDate(s.close_date, period);
      if (!bucket || !buckets.has(bucket)) continue;
      const fc = s.forecast_category ?? "";
      if (!CLAUDIO_FORECAST_CATS.has(fc)) continue;
      const key = `${s.deal_id}::${bucket}`;
      const prev = latestPerKey.get(key);
      if (!prev || new Date(s.snapshot_date) > new Date(prev.snapshot_date)) {
        latestPerKey.set(key, {
          snapshot_date: s.snapshot_date,
          amount: Number(s.amount || 0),
          fc,
          prob: s.close_probability,
        });
      }
    }
    for (const [key, v] of latestPerKey) {
      const bucket = key.split("::")[1];
      const b = buckets.get(bucket);
      if (!b) continue;
      b.team += v.amount;
      b.claudio += (v.amount * (v.prob ?? 50)) / 100;
    }

    // Actual closed
    const closedByPeriod = new Map<string, number>();
    for (const c of closed) {
      if (teamFilter && extractTeam(c.deal_name) !== teamFilter) continue;
      if (paeFilter && c.pae !== paeFilter && c.pbd !== paeFilter) continue;
      const b = periodOfDate(c.close_date, period);
      if (!b || !buckets.has(b)) continue;
      closedByPeriod.set(b, (closedByPeriod.get(b) ?? 0) + Number(c.amount || 0));
    }

    return periods.map((p) => {
      const b = buckets.get(p)!;
      return {
        period: p,
        team: Math.round(b.team),
        claudio: Math.round(b.claudio),
        actual: Math.round(closedByPeriod.get(p) ?? 0),
      };
    });
  }, [snapshots, closed, period, teamFilter, paeFilter]);

  const targetLine = period === "month" ? target : target * 3;

  // Table: sorted by close_probability desc, NULLs last
  const sortedDeals = useMemo(() => {
    return [...forecastDeals].sort((a, b) => {
      const pa = a.close_probability;
      const pb = b.close_probability;
      if (pa == null && pb == null) return 0;
      if (pa == null) return 1;
      if (pb == null) return -1;
      return pb - pa;
    });
  }, [forecastDeals]);

  if (loading) {
    return (
      <AppShell>
        <div className="text-sm text-gray-500">Loading forecast…</div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      {/* Header & filters */}
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-lg font-semibold text-gray-900">Forecast</h2>
        <div className="flex items-center gap-2">
          <select
            value={teamFilter}
            onChange={(e) => {
              setTeamFilter(e.target.value);
              setPaeFilter("");
            }}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-600"
          >
            <option value="">All Teams</option>
            <option value="Santander">Santander</option>
            <option value="Telefónica">Telefónica</option>
            <option value="TIM">TIM</option>
            <option value="TELEKOM">TELEKOM</option>
          </select>
          <select
            value={paeFilter}
            onChange={(e) => setPaeFilter(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-600"
          >
            <option value="">All PAEs</option>
            {paeOptions.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <button
            onClick={() => setShowChart((v) => !v)}
            className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg bg-white text-gray-600 hover:bg-gray-50"
          >
            {showChart ? "Hide" : "Show"} Forecast Evolution
          </button>
        </div>
      </div>

      {err && (
        <div className="mb-4 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {err}
        </div>
      )}


      {/* Cards */}
      <div className="grid grid-cols-4 gap-4 mb-5">
        <Card label="Monthly Target" value={formatAmount(target)} sub={currentMonthKey()} />
        <Card
          label="Team Forecast (HubSpot)"
          value={formatAmount(teamForecast)}
          sub={`${forecastDeals.filter((d) => d.forecast_category !== "Pipeline_new").length} deals`}
        />
        <Card
          label="Claudio Forecast (weighted)"
          value={formatAmount(claudioForecast)}
          sub={`${forecastDeals.filter((d) => CLAUDIO_FORECAST_CATS.has(d.forecast_category ?? "")).length} deals`}
        />
        <Card
          label="Actual Closed (this month)"
          value={formatAmount(actualClosedThisMonth)}
          sub={
            target > 0
              ? `${Math.round((actualClosedThisMonth / target) * 100)}% of target`
              : "—"
          }
        />
      </div>

      {/* Chart */}
      {showChart && (
        <div className="bg-white rounded-lg border border-gray-100 p-4 mb-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-gray-700">Forecast Evolution</span>
            <div className="bg-gray-50 rounded-md p-0.5 flex gap-0.5">
              {(["month", "quarter"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={`px-2.5 py-1 text-xs font-medium rounded-md ${
                    period === p
                      ? "bg-white shadow-sm text-gray-800"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {p === "month" ? "Monthly" : "Quarterly"}
                </button>
              ))}
            </div>
          </div>
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="period" tick={{ fontSize: 11, fill: "#64748b" }} />
                <YAxis
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v))}
                />
                <Tooltip
                  formatter={(v: number) => formatAmount(v)}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="team" name="Team Forecast" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                <Bar dataKey="claudio" name="Claudio Forecast" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
                <Bar dataKey="actual" name="Actual Closed" fill="#10b981" radius={[3, 3, 0, 0]} />
                {targetLine > 0 && (
                  <ReferenceLine
                    y={targetLine}
                    stroke="#ef4444"
                    strokeDasharray="4 4"
                    label={{
                      value: `Target ${formatAmount(targetLine)}`,
                      fill: "#ef4444",
                      fontSize: 11,
                      position: "right",
                    }}
                  />
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-lg border border-gray-100 overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <Th>Deal</Th>
              <Th>Owner</Th>
              <Th>HS Forecast</Th>
              <Th>Claudio Probability</Th>
              <Th className="text-center">Warnings</Th>
              <Th className="text-right">Amount</Th>
            </tr>
          </thead>
          <tbody>
            {sortedDeals.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-gray-400">
                  No deals found
                </td>
              </tr>
            )}
            {sortedDeals.map((d) => {
              const owner = d.pae || d.pbd || "—";
              const team = extractTeam(d.deal_name);
              const prob = d.close_probability;
              const probPct = prob != null ? Math.round(prob) : null;
              const probBar =
                probPct == null
                  ? "bg-gray-300"
                  : probPct >= 70
                    ? "bg-green-500"
                    : probPct >= 30
                      ? "bg-amber-400"
                      : "bg-red-400";
              const warns = countWarnings(d.live_blockers, d.objections);
              const warnColor =
                warns === 0
                  ? "bg-gray-100 text-gray-500"
                  : warns <= 2
                    ? "bg-green-100 text-green-700"
                    : warns <= 5
                      ? "bg-amber-100 text-amber-700"
                      : "bg-red-100 text-red-700";
              return (
                <tr key={d.deal_id} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="px-4 py-3">
                    <div className="text-sm font-medium text-gray-900">
                      {d.deal_name || "—"}
                    </div>
                    <div className="text-[10px] text-gray-400">
                      {team || "—"}
                      {d.claudio_close_date ? ` · Claudio: ${d.claudio_close_date}` : ""}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">{owner}</td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {d.forecast_category || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-20 bg-gray-100 rounded-full h-1.5">
                        <div
                          className={`${probBar} rounded-full h-1.5`}
                          style={{ width: `${probPct ?? 0}%` }}
                        />
                      </div>
                      <span className="text-sm text-gray-700 tabular-nums">
                        {probPct != null ? `${probPct}%` : "—"}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => warns > 0 && setWarningsFor(d)}
                      className={`inline-flex items-center justify-center w-6 h-6 rounded-full ${warnColor} text-xs font-bold ${warns > 0 ? "cursor-pointer hover:ring-2 hover:ring-offset-1 hover:ring-amber-300" : "cursor-default"}`}
                      disabled={warns === 0}
                    >
                      {warns}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right text-sm font-semibold text-gray-900">
                    {formatAmount(d.amount)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Warnings modal */}
      <Dialog open={!!warningsFor} onOpenChange={(o) => !o && setWarningsFor(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="text-base">
              {warningsFor?.deal_name || "Deal warnings"}
            </DialogTitle>
          </DialogHeader>
          {warningsFor && (
            <div className="space-y-4 text-sm">
              <WarningSection title="Live Blockers" text={warningsFor.live_blockers} />
              <WarningSection title="Objections" text={warningsFor.objections} />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}

function Card({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-100 p-4">
      <div className="text-[10px] text-gray-400 uppercase tracking-wider">{label}</div>
      <div className="text-2xl font-semibold text-gray-900 mt-1 tabular-nums">{value}</div>
      {sub && <div className="text-[11px] text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      className={`text-[10px] text-gray-400 uppercase tracking-wider font-medium px-4 py-3 text-left ${className ?? ""}`}
    >
      {children}
    </th>
  );
}

function WarningSection({ title, text }: { title: string; text: string | null }) {
  const items = (text || "")
    .split(/[\n•\-*]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 3);
  if (!items.length) {
    return (
      <div>
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          {title}
        </div>
        <div className="text-xs text-gray-400 italic">None</div>
      </div>
    );
  }
  return (
    <div>
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
        {title}
      </div>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-sm text-gray-700">
            <span className="text-amber-500 mt-0.5">•</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
