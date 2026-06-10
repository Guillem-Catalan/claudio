import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const AZURE_ENDPOINT = Deno.env.get("AZURE_CLAUDE_ENDPOINT")!;
const AZURE_KEY = Deno.env.get("AZURE_CLAUDE_API_KEY")!;
const MODEL = Deno.env.get("AZURE_CLAUDE_FAST_DEPLOYMENT") || "claudio-claude-sonnet-4-6";

const WEBHOOK_URL = "https://zuvqncurnxkocmmcvdkk.supabase.co/functions/v1/webhook-transcript-presentation";
const WEBHOOK_API_KEY = "EwMunUjVSTucXumtyIbZfhXzL1wIT9ek";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

const STAGE_TO_TYPE: Record<string, string> = {
  "Factorial Project Alignment started": "first_demo",
  "Demo Booked": "first_demo",
  "Meeting Booked": "first_demo",
  "Meeting scheduled": "first_demo",
  "Product Alignment": "first_demo",
  "Discovery": "first_demo",
  "MEDDPICC Criteria Validation Started": "meddic_review",
  "Economical Allignment Started": "pricing",
  "Economical Alignment Started": "pricing",
  "Pricing and Packaging": "pricing",
  "Pricing & Packaging": "pricing",
  "Contract Sent": "closing",
};

const BASE_PROMPT = `You are CLAUDIO — an automated Sales Team Lead for Factorial's Strategic Partnerships channel.

You will receive the full context of a deal that has an upcoming meeting. Your job is to produce a structured briefing so the PAE (Account Executive) walks into the meeting fully prepared.

The context includes: company history (atlas), PBD calls with BANT data, emails, notes, contacts, and prior meeting summaries.

Generate the briefing as a clear, structured text document with these sections:
1. RESUMEN — one-liner context of the deal and why this meeting is happening
2. ESTADO DEL DEAL — what has been covered, where the opportunity stands
3. GAPS — topics NOT covered that should be addressed
4. ESTRATEGIA — how to approach THIS specific meeting
5. ACCIONES CRÍTICAS — 3 things to do/check BEFORE the meeting
6. OBJECIONES — anticipated objections with recommended responses

Language: Spanish. Be direct and actionable. Ground every statement in evidence from the context.`;

async function callClaude(systemPrompt: string, userPrompt: string): Promise<string> {
  const baseUrl = AZURE_ENDPOINT.replace(/\/+$/, "");
  const resp = await fetch(`${baseUrl}/v1/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": AZURE_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 4000,
      system: systemPrompt,
      messages: [{ role: "user", content: userPrompt }],
    }),
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Claude error: ${resp.status} — ${err}`);
  }

  const data = await resp.json();
  return data.content?.[0]?.text || "";
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
    const { briefing_id } = await req.json();
    if (!briefing_id) {
      return new Response(JSON.stringify({ error: "briefing_id required" }), { status: 400 });
    }

    // Fetch briefing row
    const { data: briefing, error: bErr } = await sb
      .from("briefings")
      .select("*")
      .eq("id", briefing_id)
      .single();

    if (bErr || !briefing) {
      return new Response(JSON.stringify({ error: "Briefing not found" }), { status: 404 });
    }

    const dealId = briefing.deal_id;
    const useCase = briefing.use_case_key || "pae_brief_followup_meddic_multisector";

    // Fetch deal + atlas
    const { data: deal } = await sb
      .from("deals")
      .select("*, atlas:atlas_id(company_name, company_context, contacts_map, website)")
      .eq("id", dealId)
      .single();

    if (!deal) {
      await sb.from("briefings").update({ status: "error" }).eq("id", briefing_id);
      return new Response(JSON.stringify({ error: "Deal not found" }), { status: 404 });
    }

    // Fetch latest snapshot
    const { data: snaps } = await sb
      .from("front_deal_snapshots")
      .select("*")
      .eq("deal_id", dealId)
      .order("snapshot_date", { ascending: false })
      .limit(1);

    const snapshot = snaps?.[0] || null;

    // Detect meeting type from stage
    const meetingType = STAGE_TO_TYPE[deal.deal_stage] || "follow_up";

    // Build user prompt with deal context
    const dealContext = deal.deal_context || "";
    const parts: string[] = [
      `## DEAL — ${deal.deal_name || "?"}`,
      `Amount: ${deal.amount || "?"} | Stage: ${deal.deal_stage || "?"}`,
      `PBD: ${deal.pbd || "?"} | PAE: ${deal.pae || "?"}`,
      `Contacts: ${deal.contacts_info || "N/A"}`,
      `Meeting type: ${meetingType}`,
      "",
    ];

    if (deal.atlas) {
      if (deal.atlas.company_name) parts.push(`Company: ${deal.atlas.company_name}`);
      if (deal.atlas.company_context) parts.push(deal.atlas.company_context);
    }

    if (snapshot) {
      parts.push("");
      parts.push("=== SNAPSHOT ACTUAL ===");
      parts.push(`Deal Summary: ${snapshot.deal_summary || "-"}`);
      parts.push(`MEDDICC: M=${snapshot.m_score} E=${snapshot.e_score} DC=${snapshot.dc_score} DP=${snapshot.dp_score} I=${snapshot.i_score} C=${snapshot.c_score} Comp=${snapshot.comp_score}`);
      parts.push(`Buyer Signals: ${snapshot.buyer_signals || "Ninguna"}`);
      parts.push(`Live Blockers: ${snapshot.live_blockers || "Ninguno"}`);
      parts.push(`Objections: ${snapshot.objections || "Ninguna"}`);
      parts.push(`Next Step: ${snapshot.next_step || "-"}`);
    }

    parts.push("");
    parts.push("=== HISTORIAL COMPLETO ===");
    parts.push(dealContext || "(Sin interacciones registradas)");

    const userPrompt = parts.join("\n");

    // Generate briefing text with Claude
    await sb.from("briefings").update({ status: "generating" }).eq("id", briefing_id);

    const briefingText = await callClaude(BASE_PROMPT, userPrompt);

    // Determine sales_rep email
    const salesRep = deal.pae
      ? deal.pae.toLowerCase().replace(/ /g, ".") + "@factorial.co"
      : "unknown@factorial.co";

    const companyName = deal.deal_name?.split(" - ")[0]?.split(" from ")[0]?.trim() || deal.deal_name;
    const website = deal.atlas?.website || "";

    // POST to Presentation Master
    const webhookBody = {
      sales_rep: salesRep,
      transcript: briefingText,
      use_case_key: useCase,
      company_name: companyName,
      website: website,
      kind: "briefing",
      callback_slide_id: briefing_id,
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
      await sb.from("briefings").update({ status: "error" }).eq("id", briefing_id);
      return new Response(JSON.stringify({ error: "Webhook failed", detail: errText }), { status: 502 });
    }

    // Save briefing text
    await sb.from("briefings").update({
      brief: { text: briefingText, meeting_type: meetingType },
      status: "sent",
    }).eq("id", briefing_id);

    return new Response(
      JSON.stringify({ briefing_id, status: "sent" }),
      {
        status: 200,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      }
    );
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
  }
});
