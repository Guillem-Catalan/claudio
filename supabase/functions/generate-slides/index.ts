import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const WEBHOOK_URL = "https://zuvqncurnxkocmmcvdkk.supabase.co/functions/v1/webhook-transcript-presentation";
const WEBHOOK_API_KEY = "EwMunUjVSTucXumtyIbZfhXzL1wIT9ek";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

function buildTranscript(deal: any, atlas: any, snapshot: any): string {
  const parts: string[] = [];

  // Block 1: Company & lead info
  parts.push("=== 1. INFORMACIÓN DE LA EMPRESA Y LEAD ===");
  parts.push(`Empresa: ${deal.deal_name || "?"}`);
  parts.push(`Stage: ${deal.deal_stage || "?"}`);
  parts.push(`MRR: ${deal.amount || "?"}€`);
  parts.push(`PAE: ${deal.pae || "?"} | PBD: ${deal.pbd || "?"}`);
  if (deal.contacts_info) parts.push(`Contactos: ${deal.contacts_info}`);
  if (atlas) {
    if (atlas.company_name) parts.push(`Company: ${atlas.company_name}`);
    if (atlas.company_context) parts.push(atlas.company_context);
    if (atlas.contacts_map) parts.push(`Contacts map: ${atlas.contacts_map}`);
  }

  // Block 2: Pains & challenges
  parts.push("\n=== 2. DOLORES Y RETOS DEL PROSPECT ===");
  if (snapshot?.i_accumulate) parts.push(`Pain (Identify Pain): ${snapshot.i_accumulate}`);
  if (snapshot?.live_blockers) parts.push(`Blockers activos: ${snapshot.live_blockers}`);
  if (snapshot?.deal_summary) parts.push(`Resumen del deal: ${snapshot.deal_summary}`);

  // Block 3: Modules shown / interest
  parts.push("\n=== 3. MÓDULOS VISTOS E INTERÉS ===");
  if (snapshot?.dc_accumulate) parts.push(`Decision Criteria: ${snapshot.dc_accumulate}`);
  if (snapshot?.deal_strengths) parts.push(`Fortalezas: ${snapshot.deal_strengths}`);
  if (snapshot?.buyer_signals) parts.push(`Señales de compra: ${snapshot.buyer_signals}`);

  // Block 4: Objections & competition
  parts.push("\n=== 4. OBJECIONES Y COMPETENCIA ===");
  if (snapshot?.objections) parts.push(`Objeciones: ${snapshot.objections}`);
  if (snapshot?.comp_accumulate) parts.push(`Competencia: ${snapshot.comp_accumulate}`);

  // Block 5: Next step
  parts.push("\n=== 5. PRÓXIMO PASO COMERCIAL ===");
  if (snapshot?.next_step) parts.push(`Next step: ${snapshot.next_step}`);
  if (snapshot?.action_signal) parts.push(`Action signal: ${snapshot.action_signal}`);

  // Block 6: MEDDICC scores
  parts.push("\n=== 6. MEDDICC SCORES ===");
  const scores = ["m", "e", "dc", "dp", "i", "c", "comp"];
  const labels = ["Metrics", "Economic Buyer", "Decision Criteria", "Decision Process", "Identify Pain", "Champion", "Competition"];
  scores.forEach((k, i) => {
    const score = snapshot?.[`${k}_score`];
    const acc = snapshot?.[`${k}_accumulate`];
    if (score != null) {
      parts.push(`${labels[i]}: ${score}/10${acc ? ` — ${acc}` : ""}`);
    }
  });

  // Block 7: Full deal context (chronological interactions)
  if (deal.deal_context) {
    parts.push("\n=== 7. HISTORIAL COMPLETO DE INTERACCIONES ===");
    parts.push(deal.deal_context);
  }

  return parts.join("\n");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
      },
    });
  }

  try {
    const { deal_id } = await req.json();
    if (!deal_id) {
      return new Response(JSON.stringify({ error: "deal_id required" }), { status: 400 });
    }

    // Fetch deal
    const { data: deal, error: dealErr } = await sb
      .from("deals")
      .select("*, atlas:atlas_id(company_name, company_context, contacts_map, website)")
      .eq("id", deal_id)
      .single();

    if (dealErr || !deal) {
      return new Response(JSON.stringify({ error: "Deal not found" }), { status: 404 });
    }

    // Fetch latest snapshot
    const { data: snaps } = await sb
      .from("front_deal_snapshots")
      .select("*")
      .eq("deal_id", deal_id)
      .order("snapshot_date", { ascending: false })
      .limit(1);

    const snapshot = snaps?.[0] || null;

    // Build transcript
    const transcript = buildTranscript(deal, deal.atlas, snapshot);

    // Determine sales_rep email
    const salesRep = deal.pae
      ? deal.pae.toLowerCase().replace(/ /g, ".") + "@factorial.co"
      : "unknown@factorial.co";

    // Determine company website from atlas
    const website = deal.atlas?.website || "";

    // Insert pending slide
    const { data: slideRow, error: slideErr } = await sb
      .from("slides")
      .insert({
        deal_id: deal_id,
        deal_name: deal.deal_name,
        kind: "post_demo",
        status: "pending",
      })
      .select("id")
      .single();

    if (slideErr) {
      return new Response(JSON.stringify({ error: "Failed to create slide row", detail: slideErr }), { status: 500 });
    }

    // POST to webhook
    const webhookBody = {
      sales_rep: salesRep,
      transcript: transcript,
      use_case_key: "post_demo_v2",
      company_name: deal.deal_name?.split(" - ")[0]?.split(" from ")[0]?.trim() || deal.deal_name,
      website: website,
      kind: "post_demo",
      callback_slide_id: slideRow.id,
    };

    const webhookRes = await fetch(WEBHOOK_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": WEBHOOK_API_KEY,
      },
      body: JSON.stringify(webhookBody),
    });

    if (!webhookRes.ok) {
      const errText = await webhookRes.text();
      await sb.from("slides").update({ status: "error" }).eq("id", slideRow.id);
      return new Response(JSON.stringify({ error: "Webhook failed", detail: errText }), { status: 502 });
    }

    return new Response(
      JSON.stringify({ slide_id: slideRow.id, status: "pending" }),
      {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      }
    );
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
  }
});
