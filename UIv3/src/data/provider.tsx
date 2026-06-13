import { useState, useEffect, type ReactNode } from "react";
import { DataContext, type CZData, type DealRow, type FunnelStage, type ForecastDeal, type ForecastData, type ClosedDeal, type ActionItem } from "./store";
import { supabase } from "./supabase";

// ---- Stage palette ----
const STAGE: Record<string, { tone: string }> = {
  "Demo": { tone: "blue" },
  "Demo Booked": { tone: "blue" },
  "Meeting Booked": { tone: "blue" },
  "MEDDPICC": { tone: "violet" },
  "MEDDPICC Criteria Validation Started": { tone: "violet" },
  "Resched.": { tone: "amber" },
  "To reschedule": { tone: "amber" },
  "To Reschedule": { tone: "amber" },
  "Engaged": { tone: "teal" },
  "On Hold": { tone: "ink" },
  "Product": { tone: "green" },
  "Product Alignment": { tone: "green" },
  "Discovery": { tone: "blue" },
  "New": { tone: "ink" },
  "New Deals": { tone: "ink" },
  "FPA Alignment": { tone: "blue" },
  "FPA": { tone: "blue" },
  "Factorial Project Alignment started": { tone: "blue" },
  "Pipeline": { tone: "ink" },
  "Research & Outreach": { tone: "ink" },
  "Attempting to contact": { tone: "ink" },
  "Pre-qualified": { tone: "ink" },
  "Connected - Not Engaged": { tone: "ink" },
  "Qualifying": { tone: "blue" },
  "Nurturing": { tone: "amber" },
  "Sales Nurturing": { tone: "amber" },
  "Contract Sent": { tone: "indigo" },
  "Pricing & Packaging": { tone: "indigo" },
  "Pricing and Packaging": { tone: "indigo" },
  "Economical Allignment Started": { tone: "indigo" },
  "Economical Alignment Started": { tone: "indigo" },
  "Closed Won": { tone: "green" },
  "Closed Won - Finance Only": { tone: "green" },
  "Wrongly Created Ticket": { tone: "ink" },
  "Opportunity detected": { tone: "ink" },
  "Associating the partner": { tone: "ink" },
  "Econ. Align.": { tone: "indigo" },
};

const EXCLUDE = new Set([
  "Opportunity lost", "Closed lost", "Closed Lost", "Closed won", "Closed Won",
  "Closed Won - Finance Only", "Opportunity Lost",
  "Onboarding Completed - Converted", "Onboarding Completed - Pending Conversion",
  "Onboarding Failed", "Onboarding On Hold",
  "> 75% sessions done", "51-75% sessions done", "26-50% sessions done",
  "≤ 25% sessions done", "1st Session Scheduled", "Client pending to launch",
  "Churned (Closed)", "Retained (Closed)", "Preventive Churn Risk (New)",
  "Requested Churn (New)", "(DO NOT USE) Churn Confirmed",
  "Wrongly Created Ticket (Closed)", "SPAM",
]);

const STAGE_MAP: Record<string, string> = {
  "Pre-qualified": "prospecting",
  "Attempting to contact": "prospecting",
  "Research & Outreach": "prospecting",
  "Associating the partner": "prospecting",
  "Connected - Not Engaged": "prospecting",
  "New": "prospecting",
  "New Deals": "prospecting",
  "Opportunity detected": "prospecting",
  "Engaged": "qualifying",
  "Factorial Project Alignment started": "demo",
  "Demo Booked": "demo",
  "Meeting Booked": "demo",
  "Product Alignment": "demo",
  "Discovery": "demo",
  "MEDDPICC Criteria Validation Started": "evaluating",
  "Economical Allignment Started": "closing",
  "Economical Alignment Started": "closing",
  "Pricing and Packaging": "closing",
  "Pricing & Packaging": "closing",
  "Contract Sent": "closing",
  "Closed Won": "won",
  "Closed Won - Finance Only": "won",
  "On Hold": "onhold",
  "Nurturing": "nurturing",
  "Sales Nurturing": "nurturing",
  "To reschedule": "nurturing",
  "To Reschedule": "nurturing",
};

const FUNNEL_DEF = [
  { key: "prospecting", label: "Prospecting", tone: "ink" },
  { key: "qualifying", label: "Qualifying", tone: "blue" },
  { key: "nurturing", label: "Nurturing", tone: "amber" },
  { key: "demo", label: "Demo", tone: "teal" },
  { key: "evaluating", label: "Evaluating", tone: "violet" },
  { key: "closing", label: "Closing", tone: "indigo" },
  { key: "won", label: "Closed Won", tone: "green" },
];

const ASIDE_DEF = [
  { key: "onhold", label: "On Hold", tone: "amber" },
  { key: "other", label: "Other", tone: "ink" },
];

const STALE_DAYS: Record<string, number> = {
  prospecting: 21, qualifying: 14, demo: 10, evaluating: 14,
  closing: 7, won: 999, nurturing: 30, onhold: 45, other: 14,
};

function daysSince(d: string | null): number {
  if (!d) return Infinity;
  return Math.floor((Date.now() - new Date(d).getTime()) / 86_400_000);
}

function lastLabel(d: string | null): string {
  const days = daysSince(d);
  if (days === 0) return "Hoy";
  if (days === 1) return "Hace 1d";
  if (days === Infinity) return "—";
  return `Hace ${days}d`;
}

const PARTNER_DOMAINS = ["santander.com","bancosantander.es","gruposantander.com","gruposantander.es","telefonica.com","telefonica.es","sa.telecomitalia.it","telekom.de"];

async function fetchPartnerAtlasIds(): Promise<Set<string>> {
  const ids = new Set<string>();
  for (const domain of PARTNER_DOMAINS) {
    const { data } = await supabase.from("atlas").select("id").ilike("website", `%${domain}%`);
    for (const a of data || []) ids.add(a.id);
  }
  return ids;
}

// Rep name → team mapping (derived from config.py TEAMS)
const REP_TEAM: Record<string, string> = {};
// From src/config.py TEAMS — exact PAE + PBD per team
export const TEAM_REPS: Record<string, string[]> = {
  "Santander": ["Beatriz Bravo","Carlos Acosta","David Soler","Ignacio Otero","Ines Rivera","Joan Balana","Joan Lorenzo","Jose Donis","Lucia Garana","Marta Ruiz","Nicolas Gonzalez","Paula Gil","Pol Bartolome","Roberto Moran","Xavier Fortuny"],
  "Telefónica": ["Alejandro Soto","Angel Hernandez","Carlos Sanchez","David Clemente","Joan Balana","Jon Azconobieta","Maria Masoliver","Nerea Urien"],
  "TIM": ["Alessandro Cardinale","Cecilia Rinaldo","Christian Lombardo","Edoardo Rapezzi","Emilio Fabbro","Giacomo Torresi","Giuditta Giunta","Miljan Nojkic","Nunzio Fumo"],
  "TELEKOM": ["Alexander Ulrich","Chiang Nguyen","Enrique Gautier","Fiona Durr","Gabriel Lichtenstein","Johanna Henrich","Katrin Virtbauer","Leonhard Zeus","Lior Shechori","Stefan Platt"],
};
const normalize = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
for (const [team, reps] of Object.entries(TEAM_REPS)) {
  for (const rep of reps) {
    const key = normalize(rep);
    if (!REP_TEAM[key]) REP_TEAM[key] = team;
  }
}

export function repNameToEmail(name: string): string {
  return name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ /g, ".") + "@factorial.co";
}

function extractTeam(dealName: string | null, pae: string | null, pbd: string | null): string {
  // First: check deal name for team keyword (most reliable for shared reps)
  const dn = (dealName || "").toLowerCase();
  if (dn.includes("santander")) return "Santander";
  if (dn.includes("telefon") || dn.includes("telefónica")) return "Telefónica";
  if (dn.includes("from tim") || dn.includes("- tim") || dn.includes("-tim")) return "TIM";
  if (dn.includes("telekom") || dn.includes("deutsche")) return "TELEKOM";
  // Fallback: check rep → team. Names in Supabase may have extra middle names
  // e.g. "Nerea Urien Meizoso" matches "Nerea Urien", "Giuditta Francesca Speranza Giunta" matches "Giuditta Giunta"
  const name = normalize(pae || pbd || "");
  if (REP_TEAM[name]) return REP_TEAM[name];
  for (const [key, team] of Object.entries(REP_TEAM)) {
    if (name.startsWith(key + " ") || name === key) return team;
    // Match by first name + last name contained
    const parts = key.split(" ");
    if (parts.length >= 2) {
      const firstName = parts[0];
      const lastName = parts[parts.length - 1];
      if (name.startsWith(firstName + " ") && name.includes(lastName)) return team;
    }
  }
  return "";
}

function shortStage(s: string): string {
  const map: Record<string, string> = {
    "MEDDPICC Criteria Validation Started": "MEDDPICC",
    "Factorial Project Alignment started": "FPA",
    "Economical Allignment Started": "Econ. Align.",
    "Economical Alignment Started": "Econ. Align.",
    "Pricing and Packaging": "Pricing & Packaging",
    "Demo Booked": "Demo",
    "Meeting Booked": "Demo",
  };
  return map[s] || s;
}

async function fetchPaged<T>(table: string, cols: string, filter?: (q: any) => any): Promise<T[]> {
  const all: T[] = [];
  let offset = 0;
  const PAGE = 1000;
  while (true) {
    let q: any = supabase.from(table).select(cols);
    if (filter) q = filter(q);
    q = q.range(offset, offset + PAGE - 1);
    const { data, error } = await q;
    if (error) { console.warn(`[fetchPaged] ${table}: ${error.message}`); return all; }
    const rows = (data ?? []) as T[];
    all.push(...rows);
    if (rows.length < PAGE) break;
    offset += PAGE;
  }
  return all;
}

// ---- Types ----
type RawDeal = {
  id: string;
  deal_name: string | null;
  deal_stage: string | null;
  amount: number | null;
  pae: string | null;
  pbd: string | null;
  close_date: string | null;
  last_contacted_hs: string | null;
  forecast_category: string | null;
  hs_next_meeting_start_time: string | null;
  atlas_id: string | null;
  pipeline_name: string | null;
  contact_count: number | null;
  deal_age_days: number | null;
};

type RawSnap = {
  deal_id: string;
  close_probability: number | null;
  action_signal: string | null;
  live_blockers: string | null;
  next_step: string | null;
  buyer_signals: string | null;
  snapshot_date: string | null;
  m_score: number | null;
  e_score: number | null;
  dc_score: number | null;
  dp_score: number | null;
  i_score: number | null;
  c_score: number | null;
  closes_this_month: boolean | null;
  closes_next_month: boolean | null;
  forecast_pushable: boolean | null;
  push_action: string | null;
  deal_momentum: string | null;
  forecast_confidence: string | null;
  claudio_close_date: string | null;
  forecast_reasoning: string | null;
  forecast_risks: string | null;
  forecast_accelerators: string | null;
};

type RawMeeting = {
  deal_id: string;
  meeting_start: string;
};

type RawTarget = { team: string; month: string; monthly_target: number };

function buildSignal(snap: RawSnap | undefined, isStale: boolean, days: number): string {
  if (snap?.action_signal) {
    const s = snap.action_signal.trim();
    if (s) return s.length > 80 ? s.slice(0, 77) + "…" : s;
  }
  if (snap?.live_blockers) {
    const f = snap.live_blockers.split("\n")[0].replace(/^[-•!*\s]+/, "").trim();
    if (f) return ("Blocker: " + f).slice(0, 80);
  }
  if (snap?.next_step) {
    const f = snap.next_step.split("\n")[0].replace(/^[-•]\s*/, "").trim();
    if (f) return f.slice(0, 80);
  }
  if (isStale) return `Sin contacto hace ${days === Infinity ? "?" : days}d`;
  return "";
}

function extractHour(dateStr: string | null): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch { return "—"; }
}

async function loadData(): Promise<CZData> {
  const today = new Date().toISOString().slice(0, 10);

  // Fetch partner atlas IDs + deals (only active stages) + targets
  const excludeList = [...EXCLUDE];
  const [partnerIds, deals, targets] = await Promise.all([
    fetchPartnerAtlasIds(),
    fetchPaged<RawDeal>("deals", "id,deal_name,deal_stage,amount,pae,pbd,close_date,last_contacted_hs,forecast_category,hs_next_meeting_start_time,atlas_id,pipeline_name,contact_count,deal_age_days", q =>
      q.not("deal_stage", "in", `(${excludeList.join(",")})`)
    ),
    fetchPaged<RawTarget>("forecast_targets", "team,month,monthly_target"),
  ]);

  // Filter out partner deals + non-sales pipelines
  const EXCLUDE_PIPELINES = new Set(["Onboarding Pipeline", "Upselling Pipeline", "Churn Pipeline"]);
  const activeDeals = deals.filter(d => {
    if (d.atlas_id && partnerIds.has(d.atlas_id)) return false;
    if (d.pipeline_name && EXCLUDE_PIPELINES.has(d.pipeline_name)) return false;
    return true;
  });
  console.log(`[loadData] ${deals.length} raw deals, ${activeDeals.length} after partner filter (${partnerIds.size} partner atlas excluded)`);

  // Fetch snapshots only for the deals we loaded
  const dealIds = activeDeals.map(d => d.id);
  let snaps: RawSnap[] = [];
  for (let i = 0; i < dealIds.length; i += 200) {
    const batch = dealIds.slice(i, i + 200);
    const { data } = await supabase
      .from("front_deal_snapshots")
      .select("deal_id,close_probability,action_signal,live_blockers,next_step,buyer_signals,snapshot_date,m_score,e_score,dc_score,dp_score,i_score,c_score,closes_this_month,closes_next_month,forecast_pushable,push_action,deal_momentum,forecast_confidence,claudio_close_date,forecast_reasoning,forecast_risks,forecast_accelerators")
      .in("deal_id", batch)
      .order("snapshot_date", { ascending: false });
    if (data) snaps.push(...(data as RawSnap[]));
  }

  const { data: calRaw } = await supabase
    .from("calendar_meetings")
    .select("deal_id,meeting_start,pae_email")
    .gte("meeting_start", today + "T00:00:00")
    .lt("meeting_start", today + "T23:59:59")
    .eq("resolved", true)
    .not("deal_id", "is", null)
    .limit(500);
  const calMeetings = (calRaw || []) as (RawMeeting & { pae_email?: string })[];

  const { data: dmRaw } = await supabase
    .from("deal_meetings")
    .select("deal_id,meeting_start")
    .gte("meeting_start", today + "T00:00:00")
    .lt("meeting_start", today + "T23:59:59")
    .not("deal_id", "is", null)
    .limit(200);
  const dealMeetings = (dmRaw || []) as RawMeeting[];

  // Fetch unresolved calendar meetings (no deal_id — meetings sin deal vinculado)
  const { data: unresolvedRaw } = await supabase
    .from("calendar_meetings")
    .select("title,meeting_start,pae_email,pae_name")
    .gte("meeting_start", today + "T00:00:00")
    .lt("meeting_start", today + "T23:59:59")
    .is("deal_id", null)
    .limit(200);
  const unresolvedMeetings = (unresolvedRaw || []) as { title: string; meeting_start: string; pae_email: string; pae_name: string }[];

  console.log(`[loadData] ${deals.length} deals, ${snaps.length} snaps, ${calMeetings.length} cal_meetings, ${dealMeetings.length} deal_meetings, ${unresolvedMeetings.length} unresolved`);

  // Build meeting time map + meeting PAEs map
  const meetingTimeMap = new Map<string, string>();
  const meetingPaesMap = new Map<string, Set<string>>();
  for (const m of [...calMeetings, ...dealMeetings]) {
    if (!m.deal_id) continue;
    const hour = extractHour(m.meeting_start);
    const existing = meetingTimeMap.get(m.deal_id);
    if (!existing || hour < existing) meetingTimeMap.set(m.deal_id, hour);
    // Track which PAEs have this meeting in their calendar
    const paeEmail = (m as any).pae_email;
    if (paeEmail) {
      if (!meetingPaesMap.has(m.deal_id)) meetingPaesMap.set(m.deal_id, new Set());
      meetingPaesMap.get(m.deal_id)!.add(paeEmail);
    }
  }
  // Also check hs_next_meeting_start_time from deals
  for (const d of activeDeals) {
    if (!d.hs_next_meeting_start_time) continue;
    if (!d.hs_next_meeting_start_time.startsWith(today)) continue;
    const hour = extractHour(d.hs_next_meeting_start_time);
    if (!meetingTimeMap.has(d.id)) meetingTimeMap.set(d.id, hour);
  }

  // Latest + previous snapshot per deal (for trend)
  const snapsByDeal = new Map<string, RawSnap[]>();
  for (const s of snaps) {
    const arr = snapsByDeal.get(s.deal_id) || [];
    arr.push(s);
    snapsByDeal.set(s.deal_id, arr);
  }
  const snapMap = new Map<string, RawSnap>();
  const prevSnapMap = new Map<string, RawSnap>();
  for (const [dealId, arr] of snapsByDeal) {
    arr.sort((a, b) => (b.snapshot_date || "").localeCompare(a.snapshot_date || ""));
    snapMap.set(dealId, arr[0]);
    if (arr.length > 1) prevSnapMap.set(dealId, arr[1]);
  }

  // Sets for meeting classification
  const hsMeetingDealIds = new Set(dealMeetings.map(m => m.deal_id).filter(Boolean));
  const calOnlyDealIds = new Set(
    calMeetings.map(m => m.deal_id).filter(id => id && !hsMeetingDealIds.has(id))
  );
  const DEMO_STAGES = new Set(["Demo Booked", "Meeting Booked", "Factorial Project Alignment started", "Product Alignment", "Discovery"]);

  // Build deal rows
  type RowExtra = { _macro: string; _dealId: string; _amount: number; _lastDate: string | null; _fc: string | null; _closeDate: string | null; _contactCount: number; _dealAge: number; _meetingGroup: "primera-demo" | "otro-meeting" | "previsto-calendario" | null };
  const allRows: (DealRow & RowExtra)[] = [];
  for (const d of activeDeals) {
    const stage = d.deal_stage || "";
    const macro = STAGE_MAP[stage] || "other";
    const snap = snapMap.get(d.id);
    const prevSnap = prevSnapMap.get(d.id);
    const prob = snap?.close_probability ?? null;
    const days = daysSince(d.last_contacted_hs);
    const staleThreshold = STALE_DAYS[macro] || 14;
    const isStale = days > staleThreshold;

    // Trend: current prob - previous prob
    let trend: number | null = null;
    if (prob != null && prevSnap?.close_probability != null) {
      trend = prob - prevSnap.close_probability;
    }

    // Hora: from meeting sources
    const hora = meetingTimeMap.get(d.id) || "—";

    // Meeting group classification
    let meetingGroup: RowExtra["_meetingGroup"] = null;
    if (hsMeetingDealIds.has(d.id)) {
      meetingGroup = DEMO_STAGES.has(stage) ? "primera-demo" : "otro-meeting";
    } else if (calOnlyDealIds.has(d.id)) {
      meetingGroup = "previsto-calendario";
    }

    allRows.push({
      id: d.id,
      deal: d.deal_name || "—",
      team: extractTeam(d.deal_name, d.pae, d.pbd),
      stage: shortStage(stage),
      mrr: d.amount,
      prob,
      last: lastLabel(d.last_contacted_hs),
      trend,
      owner: d.pae || d.pbd || "—",
      hora,
      meetingPaes: meetingPaesMap.has(d.id) ? [...meetingPaesMap.get(d.id)!] : undefined,
      stale: isStale,
      signal: buildSignal(snap, isStale, days),
      _macro: macro,
      _dealId: d.id,
      _amount: d.amount || 0,
      _lastDate: d.last_contacted_hs,
      _fc: d.forecast_category,
      _closeDate: d.close_date,
      _contactCount: d.contact_count || 0,
      _dealAge: d.deal_age_days || 0,
      _meetingGroup: meetingGroup,
    });
  }

  // ---- Pipeline ----
  const macroGroups: Record<string, typeof allRows> = {};
  for (const r of allRows) {
    (macroGroups[r._macro] ??= []).push(r);
  }

  const pipeline: FunnelStage[] = FUNNEL_DEF.map(def => {
    const rows = macroGroups[def.key] || [];
    return {
      ...def,
      count: rows.length,
      value: rows.reduce((s, r) => s + r._amount, 0),
      stale: rows.filter(r => r.stale).length,
      rows: rows as DealRow[],
    };
  });

  const pipelineAside: FunnelStage[] = ASIDE_DEF.map(def => {
    const rows = macroGroups[def.key] || [];
    return {
      ...def,
      count: rows.length,
      value: rows.reduce((s, r) => s + r._amount, 0),
      stale: rows.filter(r => r.stale).length,
      rows: rows as DealRow[],
    };
  });

  // ---- Deals Hoy (3 groups) ----
  const sortByHora = (a: DealRow, b: DealRow) => (a.hora || "zz").localeCompare(b.hora || "zz");
  const fmtGroupMeta = (rows: DealRow[]) => {
    const mrr = rows.reduce((s, r) => s + (r.mrr || 0), 0);
    return `${rows.length} deals · €${mrr >= 1000 ? (mrr / 1000).toFixed(1) + "K" : mrr}`;
  };

  const primerasDemos = allRows.filter(r => r._meetingGroup === "primera-demo").sort(sortByHora);
  const otrosMeetings = allRows.filter(r => r._meetingGroup === "otro-meeting").sort(sortByHora);
  const previstosCalendario = allRows.filter(r => r._meetingGroup === "previsto-calendario").sort(sortByHora);

  const todayGroups = [];
  if (primerasDemos.length) {
    todayGroups.push({
      id: "primeras-demos",
      title: "Primeras demos hoy",
      meta: fmtGroupMeta(primerasDemos),
      tint: "indigo",
      rows: primerasDemos as DealRow[],
    });
  }
  if (otrosMeetings.length) {
    todayGroups.push({
      id: "otros-meetings",
      title: "Otros meetings hoy",
      meta: fmtGroupMeta(otrosMeetings),
      tint: "teal",
      rows: otrosMeetings as DealRow[],
    });
  }
  if (previstosCalendario.length) {
    todayGroups.push({
      id: "previstos-calendario",
      title: "Previstos en calendario",
      meta: fmtGroupMeta(previstosCalendario),
      tint: "violet",
      rows: previstosCalendario as DealRow[],
    });
  }

  // Unresolved meetings — calendar events not matched to any deal
  if (unresolvedMeetings.length) {
    // Deduplicate by title+time (same meeting in multiple PAE calendars)
    const seen = new Set<string>();
    const unresolvedRows: DealRow[] = [];
    for (const m of unresolvedMeetings) {
      const key = m.title + "|" + m.meeting_start;
      if (seen.has(key)) {
        // Add this PAE email to the existing row's meetingPaes
        const existing = unresolvedRows.find(r => r.deal === (m.title || "Sin título") && r.hora === extractHour(m.meeting_start));
        if (existing && existing.meetingPaes && !existing.meetingPaes.includes(m.pae_email)) {
          existing.meetingPaes.push(m.pae_email);
        }
        continue;
      }
      seen.add(key);
      unresolvedRows.push({
        deal: m.title || "Sin título",
        stage: "⚠ Sin deal",
        mrr: null,
        prob: null,
        last: "—",
        trend: null,
        owner: m.pae_name || "—",
        team: extractTeam(null, m.pae_name, null),
        hora: extractHour(m.meeting_start),
        meetingPaes: [m.pae_email],
        stale: false,
        signal: "",
      });
    }
    unresolvedRows.sort((a, b) => (a.hora || "zz").localeCompare(b.hora || "zz"));
    todayGroups.push({
      id: "sin-deal",
      title: "⚠ Meetings sin deal vinculado",
      meta: `${unresolvedRows.length} meetings`,
      tint: "red",
      rows: unresolvedRows,
    });
  }

  // ---- Forecast v2 ----
  const cm = new Date().toISOString().slice(0, 7);
  const targetTotal = targets.filter(t => t.month === cm).reduce((s, t) => s + (t.monthly_target || 0), 0);

  // Build ForecastDeal for every active deal
  // Use claudio_close_date to override closes_this/next_month when they contradict
  const nextMonthKey = cm.slice(0, 5) + String(Number(cm.slice(5)) + 1).padStart(2, "0");
  const allFcDeals: ForecastDeal[] = allRows.map(r => {
    const snap = snapMap.get(r.id || "");
    const ccd = snap?.claudio_close_date || "";
    const ccdMonth = ccd.slice(0, 7);
    let closesThis = snap?.closes_this_month || false;
    let closesNext = snap?.closes_next_month || false;
    // Fix: if claudio_close_date is this month but closes_this_month=false, override
    if (ccdMonth === cm && !closesThis) { closesThis = true; closesNext = false; }
    // Fix: if claudio_close_date is next month but closes_next_month=false
    if (ccdMonth === nextMonthKey && !closesNext) { closesNext = true; closesThis = false; }
    return {
      ...r,
      closesThisMonth: closesThis,
      closesNextMonth: closesNext && !closesThis,
      pushable: snap?.forecast_pushable || false,
      pushAction: snap?.push_action || null,
      momentum: snap?.deal_momentum || null,
      confidence: snap?.forecast_confidence || null,
      claudioCloseDate: snap?.claudio_close_date || null,
      forecastReasoning: snap?.forecast_reasoning || null,
      forecastRisks: snap?.forecast_risks || null,
      forecastAccelerators: snap?.forecast_accelerators || null,
      hsCategory: r._fc || "",
      closeDate: r._closeDate || null,
    };
  });

  // HS forecast deals (Commit + Upside + Pipeline_new)
  const hsDeals = allFcDeals.filter(d => d.hsCategory === "Commit" || d.hsCategory === "Upside" || d.hsCategory === "Pipeline_new");
  const hsTotal = hsDeals.filter(d => d.hsCategory === "Commit" || d.hsCategory === "Upside").reduce((s, d) => s + (d.mrr || 0), 0);

  // Closzr forecast (closes_this_month = true)
  const closzrDeals = allFcDeals.filter(d => d.closesThisMonth);
  const closzrTotal = closzrDeals.reduce((s, d) => s + (d.mrr || 0), 0);

  // Next month (closes_next_month AND NOT this month)
  const nextMonthDeals = allFcDeals.filter(d => d.closesNextMonth && !d.closesThisMonth);
  const nextMonthTotal = nextMonthDeals.reduce((s, d) => s + (d.mrr || 0), 0);

  // Pushable (NOT already in forecast YES or next month)
  const pushableDeals = allFcDeals.filter(d => d.pushable && !d.closesThisMonth && !d.closesNextMonth);

  // Closed Won this month
  const CLOSED_WON = ["Closed Won", "Closed won", "Closed Won - Finance Only"];
  const nextMonthStr = cm.slice(0, 5) + String(Number(cm.slice(5)) + 1).padStart(2, "0");
  const { data: closedRaw } = await supabase
    .from("deals")
    .select("id,deal_name,deal_stage,amount,pae,pbd,close_date,deal_age_days")
    .in("deal_stage", CLOSED_WON)
    .gte("close_date", cm + "-01")
    .lt("close_date", nextMonthStr + "-01");

  // Enrich closed deals with snapshot strengths + trajectory lessons
  const closedIds = (closedRaw || []).map((d: any) => d.id);
  const closedSnapsMap = new Map<string, any>();
  const closedTrajMap = new Map<string, any>();
  if (closedIds.length) {
    const { data: cSnaps } = await supabase
      .from("front_deal_snapshots")
      .select("deal_id,deal_strengths")
      .in("deal_id", closedIds)
      .order("snapshot_date", { ascending: false });
    for (const s of cSnaps || []) {
      if (!closedSnapsMap.has(s.deal_id)) closedSnapsMap.set(s.deal_id, s);
    }
    const { data: cTrajs } = await supabase
      .from("deal_trajectories")
      .select("deal_id,lessons,interactions,deal_age_days")
      .in("deal_id", closedIds);
    for (const t of cTrajs || []) closedTrajMap.set(t.deal_id, t);
  }

  const closedDeals: ClosedDeal[] = (closedRaw || []).map((d: any) => {
    const snap = closedSnapsMap.get(d.id);
    const traj = closedTrajMap.get(d.id);
    let lessons: string[] = [];
    if (traj?.lessons) {
      try { lessons = typeof traj.lessons === "string" ? JSON.parse(traj.lessons) : traj.lessons; } catch {}
    }
    let interactions = null;
    if (traj?.interactions) {
      try { interactions = typeof traj.interactions === "string" ? JSON.parse(traj.interactions) : traj.interactions; } catch {}
    }
    return {
      id: d.id, deal: d.deal_name || "—", stage: d.deal_stage || "Closed Won", mrr: d.amount,
      prob: 100, last: d.close_date || "—", trend: null, owner: d.pae || d.pbd || "—",
      team: extractTeam(d.deal_name, d.pae, d.pbd),
      dealAge: traj?.deal_age_days || d.deal_age_days || null,
      strengths: snap?.deal_strengths || null,
      lessons,
      interactions,
    };
  });
  const closedTotal = closedDeals.reduce((s, d) => s + (d.mrr || 0), 0);

  const forecast: ForecastData = {
    target: targetTotal,
    hsTotal: Math.round(hsTotal),
    closzrTotal: Math.round(closzrTotal),
    nextMonthTotal: Math.round(nextMonthTotal),
    pushableCount: pushableDeals.length,
    closedTotal: Math.round(closedTotal),
    hsDeals,
    closzrDeals,
    nextMonthDeals,
    pushableDeals,
    closedDeals,
    allDeals: allFcDeals,
    targets,
  };

  // ---- 1:1 ----
  const reps = [...new Set(allRows.map(r => r.owner).filter(o => o !== "—"))].sort();
  const rep = reps[0] || "—";
  const repDeals = allRows.filter(r => r.owner === rep);
  const todayStr = new Date().toISOString().slice(0, 10);

  // TL Actions: deals with blockers or no contact >14 days
  const tlActions = repDeals.filter(r => {
    const snap = snapMap.get(r.id || "");
    const days = daysSince(r._lastDate);
    return (snap?.live_blockers && snap.live_blockers.trim().length > 5) || days > 14;
  }).sort((a, b) => (b._amount || 0) - (a._amount || 0)).slice(0, 10).map(r => {
    const snap = snapMap.get(r.id || "");
    const days = daysSince(r._lastDate);
    const hasBlocker = snap?.live_blockers && snap.live_blockers.trim().length > 5;
    const firstBlocker = hasBlocker ? snap!.live_blockers!.split("\n")[0].replace(/^[-•!*\s]+/, "").trim().slice(0, 80) : "";
    return {
      id: r.id, deal: r.deal, stage: r.stage, mrr: r.mrr, prob: r.prob,
      flag: hasBlocker ? "Blocker activo" : `Sin contacto ${days}d`,
      sev: hasBlocker || days > 30 ? "alto" : "medio",
      text: hasBlocker ? firstBlocker : `Último contacto hace ${days} días — empujar re-engagement.`,
    };
  });

  // Hygiene: count deals per issue + include deal lists
  const singleContact = repDeals.filter(r => r._contactCount <= 1);
  const longPipeline = repDeals.filter(r => r._dealAge >= 45);
  const pastClose = repDeals.filter(r => r._closeDate && r._closeDate < todayStr);
  const noContact30 = repDeals.filter(r => daysSince(r._lastDate) > 30);
  const methodology = [
    { n: singleContact.length, label: "Solo 1 contacto", tone: singleContact.length > 10 ? "red" : "amber", key: "single_contact", deals: singleContact as DealRow[] },
    { n: longPipeline.length, label: "45+ días en pipeline", tone: "amber", key: "long_pipeline", deals: longPipeline as DealRow[] },
    { n: pastClose.length, label: "Fecha de cierre pasada", tone: "red", key: "past_close", deals: pastClose as DealRow[] },
    { n: noContact30.length, label: "Sin contacto en 30+ días", tone: "amber", key: "no_contact", deals: noContact30 as DealRow[] },
  ].filter(m => m.n > 0);

  // MEDDIC averages from real snapshots
  const repSnaps = repDeals.map(r => snapMap.get(r.id || "")).filter(Boolean) as RawSnap[];
  const avg = (field: keyof RawSnap) => {
    const vals = repSnaps.map(s => s[field] as number | null).filter(v => v != null) as number[];
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length * 10) / 10 : 0;
  };
  const meddicScores = [
    { key: "Metrics", score: avg("m_score") },
    { key: "Economic Buyer", score: avg("e_score") },
    { key: "Decision Criteria", score: avg("dc_score") },
    { key: "Decision Process", score: avg("dp_score") },
    { key: "Identify Pain", score: avg("i_score") },
    { key: "Champion", score: avg("c_score") },
  ];
  const weakest = [...meddicScores].sort((a, b) => a.score - b.score);
  const meddicNote = weakest[0] && weakest[1]
    ? `${weakest[0].key} (${weakest[0].score}) y ${weakest[1].key} (${weakest[1].score}) son las áreas más débiles. Enfoca el coaching en estas dimensiones.`
    : "";

  // Weakness: deals with score <4 per dimension
  const weakness = [
    { label: "Metrics", count: repSnaps.filter(s => (s.m_score || 0) < 4).length },
    { label: "Economic Buyer", count: repSnaps.filter(s => (s.e_score || 0) < 4).length },
    { label: "Decision Process", count: repSnaps.filter(s => (s.dp_score || 0) < 4).length },
    { label: "Champion", count: repSnaps.filter(s => (s.c_score || 0) < 4).length },
    { label: "Decision Criteria", count: repSnaps.filter(s => (s.dc_score || 0) < 4).length },
    { label: "Identify Pain", count: repSnaps.filter(s => (s.i_score || 0) < 4).length },
  ].sort((a, b) => b.count - a.count);

  const oneOnOne = {
    reps,
    rep,
    activeDeals: repDeals.length,
    pipeline: repDeals.reduce((s, r) => s + r._amount, 0),
    top10: [...repDeals].sort((a, b) => (b._amount || 0) - (a._amount || 0)).slice(0, 10).map(r => ({
      id: r.id, deal: r.deal, stage: r.stage, mrr: r.mrr, prob: r.prob,
    })),
    meddicBase: repSnaps.length,
    meddic: meddicScores,
    meddicNote,
    weakness,
    tlActions,
    methodologyOpen: repDeals.length,
    methodology,
  };

  // ---- TO-DOs: fetch deal_actions ----
  const { data: actionsRaw } = await supabase
    .from("deal_actions")
    .select("*")
    .eq("status", "pending")
    .order("action_priority")
    .limit(500);

  const todos: ActionItem[] = (actionsRaw || []).map((a: any) => {
    let followUps: ActionItem["followUps"] = [];
    try { followUps = typeof a.follow_ups === "string" ? JSON.parse(a.follow_ups) : (a.follow_ups || []); } catch {}
    return {
      id: a.id,
      dealId: a.deal_id,
      dealName: a.deal_name || "—",
      dealOwner: a.deal_owner || "—",
      dealMrr: a.deal_mrr,
      dealStage: a.deal_stage || "—",
      bucket: a.bucket || "pipeline",
      claudioCloseDate: a.claudio_close_date,
      actionHeadline: a.action_headline,
      actionDetail: a.action_detail,
      actionType: a.action_type || "PREP",
      actionWho: a.action_who || "—",
      actionWhen: a.action_when || "pendiente",
      actionPriority: a.action_priority || 3,
      actionDueDate: a.action_due_date || null,
      followUps,
      status: a.status || "pending",
      team: extractTeam(a.deal_name, a.deal_owner, null),
    };
  });

  return {
    STAGE,
    groups: todayGroups,
    nakiva: null,
    yukAtlas: null,
    pipeline,
    pipelineAside,
    forecast,
    oneOnOne,
    todos,
    loading: false,
  };
}

// ---- Provider ----
export function DataProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<CZData>({
    STAGE,
    groups: [],
    nakiva: null,
    yukAtlas: null,
    pipeline: [],
    pipelineAside: [],
    forecast: { target: 0, hsTotal: 0, closzrTotal: 0, nextMonthTotal: 0, pushableCount: 0, closedTotal: 0, hsDeals: [], closzrDeals: [], nextMonthDeals: [], pushableDeals: [], closedDeals: [], allDeals: [], targets: [] },
    oneOnOne: { reps: [], rep: "", activeDeals: 0, pipeline: 0, top10: [], meddicBase: 0, meddic: [], meddicNote: "", weakness: [], tlActions: [], methodologyOpen: 0, methodology: [] },
    todos: [],
    loading: true,
  });

  useEffect(() => {
    loadData().then(setData).catch(err => {
      console.error("Failed to load data:", err);
      setData(prev => ({ ...prev, loading: false }));
    });

    let reloadTimer: ReturnType<typeof setTimeout>;
    const debouncedReload = () => {
      clearTimeout(reloadTimer);
      reloadTimer = setTimeout(() => { loadData().then(setData); }, 5000);
    };

    const ch = supabase
      .channel("rt-all")
      .on("postgres_changes", { event: "*", schema: "public", table: "deals" }, debouncedReload)
      .on("postgres_changes", { event: "*", schema: "public", table: "front_deal_snapshots" }, debouncedReload)
      .on("postgres_changes", { event: "*", schema: "public", table: "deal_meetings" }, debouncedReload)
      .on("postgres_changes", { event: "*", schema: "public", table: "calendar_meetings" }, debouncedReload)
      .subscribe();

    return () => { clearTimeout(reloadTimer); supabase.removeChannel(ch); };
  }, []);

  return (
    <DataContext.Provider value={data}>
      {children}
    </DataContext.Provider>
  );
}
