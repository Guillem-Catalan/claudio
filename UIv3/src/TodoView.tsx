/* ============================================================
   CLOSZR — TO-DOs: daily action list for reps
   ============================================================ */
import { useState, useMemo } from "react";
import { Icon, Chip, StageChip, fmtMRR } from "./components";
import { useData } from "./data/store";
import type { ActionItem } from "./data/store";
import { TEAM_REPS } from "./data/provider";
import { supabase } from "./data/supabase";

type TimeFilter = "hoy" | "semana" | "next_week" | "mes";

const BUCKET_STYLE: Record<string, { label: string; tone: string }> = {
  forecast: { label: "Forecast", tone: "green" },
  pushable: { label: "Pushable", tone: "amber" },
  next_month: { label: "Próx. mes", tone: "blue" },
  blocker: { label: "Blocker", tone: "red" },
  pipeline: { label: "Pipeline", tone: "ink" },
  meeting: { label: "Meeting", tone: "indigo" },
};

const TYPE_ICON: Record<string, string> = {
  CALL: "phone", EMAIL: "mail", ROI: "calculator",
  SLIDES: "presentation", BATTLECARD: "shield", PREP: "sparkle",
};

function getSpainToday(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Madrid" });
}

function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function getEndOfWeek(dateStr: string): string {
  const d = new Date(dateStr);
  const dayOfWeek = d.getDay();
  const daysToFriday = dayOfWeek <= 5 ? 5 - dayOfWeek : 0;
  d.setDate(d.getDate() + daysToFriday);
  return d.toISOString().slice(0, 10);
}

function getEndOfMonth(dateStr: string): string {
  const d = new Date(dateStr);
  return new Date(d.getFullYear(), d.getMonth() + 1, 0).toISOString().slice(0, 10);
}

function matchesTimeFilter(a: ActionItem, filter: TimeFilter): boolean {
  const today = getSpainToday();
  const due = a.actionDueDate || "2099-12-31";

  if (filter === "mes") {
    return due <= getEndOfMonth(today);
  }
  if (filter === "hoy") {
    return due <= today;
  }
  if (filter === "semana") {
    return due <= getEndOfWeek(today);
  }
  if (filter === "next_week") {
    const nextMonday = addDays(getEndOfWeek(today), 3);
    const nextFriday = addDays(nextMonday, 4);
    return due > getEndOfWeek(today) && due <= nextFriday;
  }
  return true;
}

function TodoRow({ a, onOpen, onComplete }: { a: ActionItem; onOpen: () => void; onComplete: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const bs = BUCKET_STYLE[a.bucket] || BUCKET_STYLE.pipeline;

  return (
    <>
      <div className="cz-fctable-r" style={{ cursor: "pointer", gridTemplateColumns: "32px minmax(250px,1fr) 90px 80px 80px 80px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <button
            onClick={e => { e.stopPropagation(); onComplete(); }}
            style={{
              width: 22, height: 22, borderRadius: 99, border: "2px solid var(--line-ink)",
              display: "flex", alignItems: "center", justifyContent: "center",
              background: "none", cursor: "pointer", transition: "all .15s",
            }}
            title="Marcar como hecho"
          >
            <Icon name="check" size={12} stroke={2.5} style={{ color: "var(--ink-4)" }} />
          </button>
        </div>
        <div onClick={() => setExpanded(!expanded)} style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
            <Chip tone={bs.tone} style={{ fontSize: 10, padding: "1px 7px" }}>
              <Icon name={TYPE_ICON[a.actionType] || "sparkle"} size={10} stroke={2} />{" "}{a.actionType}
            </Chip>
            <Chip tone={bs.tone} style={{ fontSize: 10, padding: "1px 7px" }}>{bs.label}</Chip>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{a.actionWhen}</span>
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)", lineHeight: 1.4 }}>
            {a.actionWho && a.actionWho !== "—" && <span style={{ color: "var(--indigo)", fontWeight: 700 }}>{a.actionWho} → </span>}
            {a.actionHeadline}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {a.dealName} · {fmtMRR(a.dealMrr)} · {a.dealStage}{a.claudioCloseDate ? ` · Cierre: ${a.claudioCloseDate}` : ""}
          </div>
        </div>
        <div><StageChip stage={a.dealStage} /></div>
        <div className="num" style={{ fontWeight: 700 }}>{fmtMRR(a.dealMrr)}</div>
        <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{a.dealOwner}</div>
        <div>
          <button className="cz-btn-soft" style={{ fontSize: 11, padding: "4px 10px" }} onClick={e => { e.stopPropagation(); onOpen(); }}>
            Deal <Icon name="arrowRight" size={11} stroke={2} />
          </button>
        </div>
        <div onClick={() => setExpanded(!expanded)}>
          <Icon name="chevDown" size={14} style={{ color: "var(--ink-3)", transform: expanded ? "none" : "rotate(-90deg)", transition: "transform .18s" }} />
        </div>
      </div>
      {expanded && (
        <div style={{ padding: "14px 22px 18px 54px", background: "var(--card-2)", borderBottom: "1px solid var(--line-2)", display: "flex", flexDirection: "column", gap: 10 }}>
          {a.actionDetail && (
            <div style={{ fontSize: 13, lineHeight: 1.55, color: "var(--ink-2)" }}>{a.actionDetail}</div>
          )}
          {a.followUps.length > 0 && (
            <div>
              <span className="eyebrow" style={{ display: "block", marginBottom: 6 }}>Siguientes pasos</span>
              <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 5 }}>
                {a.followUps.map((f, i) => (
                  <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 13, lineHeight: 1.5, color: "var(--ink-2)" }}>
                    <Chip tone="ink" style={{ fontSize: 9, padding: "0px 5px", flex: "none", marginTop: 3 }}>{f.type}</Chip>
                    <span>
                      {f.who && <b>{f.who} → </b>}
                      {f.text}
                      {f.when !== "pendiente" && <span style={{ color: "var(--ink-3)" }}> — {f.when}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default function TodoView({ onOpen }: { onOpen: (row: any, tab: string) => void }) {
  const D = useData();
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("hoy");
  const [teamFilter, setTeamFilter] = useState("");
  const [repFilter, setRepFilter] = useState("");
  const [search, setSearch] = useState("");
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set());

  const teams = useMemo(() => Object.keys(TEAM_REPS).sort(), []);
  const reps = useMemo(() => {
    if (teamFilter && TEAM_REPS[teamFilter]) return [...TEAM_REPS[teamFilter]].sort();
    return [...new Set(D.todos.map(a => a.dealOwner).filter(o => o && o !== "—"))].sort();
  }, [D.todos, teamFilter]);

  const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const repNorm = repFilter ? norm(repFilter) : "";

  const filtered = useMemo(() => {
    let items = D.todos.filter(a => !completedIds.has(a.id));
    items = items.filter(a => matchesTimeFilter(a, timeFilter));
    if (teamFilter) items = items.filter(a => a.team === teamFilter);
    if (repFilter) items = items.filter(a => {
      const on = norm(a.dealOwner || "");
      return on === repNorm || on.startsWith(repNorm + " ") || norm(a.actionWho || "") === repNorm || norm(a.actionWho || "").startsWith(repNorm + " ");
    });
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter(a => a.dealName.toLowerCase().includes(q) || (a.actionHeadline || "").toLowerCase().includes(q) || (a.dealOwner || "").toLowerCase().includes(q));
    }
    return items.sort((a, b) => a.actionPriority - b.actionPriority || (b.dealMrr || 0) - (a.dealMrr || 0));
  }, [D.todos, timeFilter, teamFilter, repFilter, search, completedIds, repNorm]);

  // KPIs
  const todayCount = D.todos.filter(a => !completedIds.has(a.id) && matchesTimeFilter(a, "hoy")).length;
  const forecastCount = filtered.filter(a => a.bucket === "forecast").length;
  const pushableCount = filtered.filter(a => a.bucket === "pushable").length;
  const completedCount = completedIds.size;

  const handleComplete = async (id: string) => {
    setCompletedIds(prev => new Set(prev).add(id));
    try {
      await supabase.from("deal_actions").update({ status: "done", completed_at: new Date().toISOString() }).eq("id", id);
    } catch {}
  };

  const handleOpen = (a: ActionItem) => {
    onOpen({ id: a.dealId, deal: a.dealName, stage: a.dealStage, mrr: a.dealMrr, owner: a.dealOwner }, "hist");
  };

  return (
    <div className="cz-fc">
      {/* Toolbar */}
      <div className="cz-toolbar" style={{ marginBottom: 4 }}>
        <div className="cz-tb-title">
          <h2 className="display">TO-DOs</h2>
        </div>
        <div className="cz-seg">
          {([["hoy", "Hoy"], ["semana", "Semana"], ["next_week", "Next week"], ["mes", "Mes"]] as const).map(([k, l]) => (
            <button key={k} className={timeFilter === k ? "on" : ""} onClick={() => setTimeFilter(k)}>{l}</button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <select className="cz-native-select" value={teamFilter} onChange={e => { setTeamFilter(e.target.value); setRepFilter(""); }}>
          <option value="">All Teams</option>
          {teams.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select className="cz-native-select" value={repFilter} onChange={e => setRepFilter(e.target.value)}>
          <option value="">All PAEs/PBDs</option>
          {reps.map((r: string) => <option key={r} value={r}>{r}</option>)}
        </select>
        <label className="cz-search">
          <Icon name="search" size={16} style={{ color: "var(--ink-3)" }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar…" />
        </label>
      </div>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
        <div className="cz-fc-kpi" style={{ padding: "14px 16px" }}>
          <span className="eyebrow">Pendientes hoy</span>
          <div className="cz-fc-kpi-v display" style={{ fontSize: 26 }}>{todayCount}</div>
        </div>
        <div className="cz-fc-kpi" style={{ padding: "14px 16px" }}>
          <span className="eyebrow" style={{ color: "var(--green-ink)" }}>Forcasteados</span>
          <div className="cz-fc-kpi-v display" style={{ fontSize: 26, color: "var(--green)" }}>{forecastCount}</div>
        </div>
        <div className="cz-fc-kpi" style={{ padding: "14px 16px" }}>
          <span className="eyebrow" style={{ color: "var(--amber-ink)" }}>Pushable</span>
          <div className="cz-fc-kpi-v display" style={{ fontSize: 26, color: "var(--amber)" }}>{pushableCount}</div>
        </div>
        <div className="cz-fc-kpi" style={{ padding: "14px 16px" }}>
          <span className="eyebrow">Completados</span>
          <div className="cz-fc-kpi-v display" style={{ fontSize: 26, color: "var(--green)" }}>{completedCount}</div>
        </div>
      </div>

      {/* Action list */}
      <div className="cz-card cz-fctablecard">
        <div className="cz-fctable-top">
          <div>
            <span className="eyebrow">Acciones</span>
            <span className="cz-fctable-sub num">{filtered.length} pendientes</span>
          </div>
          <label className="cz-search" style={{ minWidth: 180 }}>
            <Icon name="search" size={16} style={{ color: "var(--ink-3)" }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar deal…" />
          </label>
        </div>

        <div className="cz-fctable">
          <div className="cz-fctable-h" style={{ gridTemplateColumns: "32px minmax(250px,1fr) 90px 80px 80px 80px 24px" }}>
            <div />
            <div>Acción</div>
            <div>Stage</div>
            <div>MRR</div>
            <div>Owner</div>
            <div />
            <div />
          </div>
          {filtered.map(a => (
            <TodoRow
              key={a.id}
              a={a}
              onOpen={() => handleOpen(a)}
              onComplete={() => handleComplete(a.id)}
            />
          ))}
          {!filtered.length && (
            <div className="cz-empty">
              {completedIds.size > 0 ? "Todas las acciones completadas. Buen trabajo." : "Sin acciones pendientes para estos filtros."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
