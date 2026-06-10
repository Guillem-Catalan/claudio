import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import type { Deal, Snapshot } from "@/lib/deals-domain";
import { EXCLUDE_STAGES } from "@/lib/deals-domain";

/**
 * Live deals + snapshots. Mirrors the original setupRealtime() behavior:
 * subscribes to `deals` and `snapshots` postgres_changes and patches state
 * locally so the UI always reflects the latest row state without refetch.
 */
export function useDeals() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [snapshots, setSnapshots] = useState<Map<string | number, Snapshot>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    (async () => {
      try {
        const [{ data: dRows, error: dErr }, { data: sRows, error: sErr }] = await Promise.all([
          supabase.from("deals").select("*").limit(5000),
          supabase.from("snapshots").select("*").limit(5000),
        ]);
        if (dErr) throw dErr;
        if (sErr) throw sErr;
        if (!mounted) return;

        const filtered = (dRows ?? []).filter(
          (d) => !EXCLUDE_STAGES.has(((d as Deal).deal_stage ?? "") as string),
        ) as Deal[];

        setDeals(filtered);
        const map = new Map<string | number, Snapshot>();
        for (const s of (sRows ?? []) as Snapshot[]) map.set(s.deal_id, s);
        setSnapshots(map);
      } catch (e) {
        if (mounted) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (mounted) setLoading(false);
      }
    })();

    const dealsCh = supabase
      .channel("rt-deals")
      .on("postgres_changes", { event: "*", schema: "public", table: "deals" }, (payload) => {
        setDeals((prev) => {
          const next = [...prev];
          const row = (payload.new ?? payload.old) as Deal | undefined;
          if (!row) return prev;
          if (payload.eventType === "DELETE") return prev.filter((d) => d.id !== row.id);
          const idx = next.findIndex((d) => d.id === row.id);
          const isExcluded = EXCLUDE_STAGES.has((row.deal_stage ?? "") as string);
          if (isExcluded) return idx >= 0 ? prev.filter((d) => d.id !== row.id) : prev;
          if (idx >= 0) next[idx] = row;
          else next.push(row);
          return next;
        });
      })
      .subscribe();

    const snapsCh = supabase
      .channel("rt-snapshots")
      .on("postgres_changes", { event: "*", schema: "public", table: "snapshots" }, (payload) => {
        setSnapshots((prev) => {
          const next = new Map(prev);
          const row = (payload.new ?? payload.old) as Snapshot | undefined;
          if (!row) return prev;
          if (payload.eventType === "DELETE") next.delete(row.deal_id);
          else next.set(row.deal_id, row);
          return next;
        });
      })
      .subscribe();

    return () => {
      mounted = false;
      supabase.removeChannel(dealsCh);
      supabase.removeChannel(snapsCh);
    };
  }, []);

  return { deals, snapshots, loading, error };
}
