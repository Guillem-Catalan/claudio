import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const AZURE_ENDPOINT = Deno.env.get("AZURE_CLAUDE_ENDPOINT")!;
const AZURE_KEY = Deno.env.get("AZURE_CLAUDE_API_KEY")!;
const MODEL = Deno.env.get("AZURE_CLAUDE_FAST_DEPLOYMENT") || "claude-sonnet-4-6";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

const STAGE_TO_TYPE: Record<string, string> = {
  "Factorial Project Alignment started": "first_demo",
  "FPA": "first_demo",
  "Demo Booked": "first_demo",
  "Meeting Booked": "first_demo",
  "Meeting scheduled": "first_demo",
  "Product Alignment": "first_demo",
  "Discovery": "first_demo",
  "MEDDPICC Criteria Validation": "meddic_review",
  "Economical Allignment": "pricing",
  "Pricing and Packaging": "pricing",
  "Contract Sent": "closing",
};

// ── Prompts ───────────────────────────────────────────────────────────────

const BASE_PROMPT = `You are CLAUDIO — an automated Sales Team Lead for Factorial's Strategic Partnerships channel.

You will receive the full context of a deal that has an upcoming meeting. Your job is to produce a structured briefing so the PAE (Account Executive) walks into the meeting fully prepared.

OUTPUT — return a single JSON object. The object MUST contain all base fields below. Additional type-specific fields are defined in the meeting type section that follows.

BASE FIELDS (required for all meeting types):
{
  "tipo": "<meeting_type>",
  "resumen": "One-liner: context of the deal and why this meeting is happening",
  "estado_deal": "Real state of the deal: what has been covered, what has been discussed, where the opportunity actually stands",
  "gaps": ["Topic NOT covered in previous meetings", "Data point still missing"],
  "estrategia": "How to approach THIS meeting to advance toward close. What to open with, emphasize, close.",
  "acciones_criticas": ["Prep action 1", "Prep action 2", "Prep action 3"],
  "objeciones": [{"pregunta": "Anticipated objection", "respuesta": "How to handle it"}]
}

RULES:
- Language: Spanish
- Be direct and actionable
- Ground every statement in evidence from the context
- If information is missing, say what's unknown
- Never invent data
- "gaps": 2-5 items, "acciones_criticas": exactly 3, "objeciones": 2-4
- Return ONLY the JSON. No text before or after. No markdown fences.`;

const TYPE_PROMPTS: Record<string, string> = {
  first_demo: `MEETING TYPE: FIRST DEMO
Include these EXTRA fields:
{
  "pepm": "€X.XX" or null,
  "empleados": "XXX" or null,
  "solucion": "Product mentioned" or null,
  "cliente": ["Sector/industry", "Size", "Decision-makers", "Relationship with Factorial"],
  "situacion": ["Current HR solution", "Why evaluating Factorial", "Where in buying process"],
  "pain_principal": {"titulo": "SHORT TITLE IN CAPS", "texto": "Evidence-based detail"},
  "pains_secundarios": ["Secondary pain with evidence"],
  "bant": {
    "budget": {"emoji": "✅ or ⚠️ or ❌", "text": "Status + evidence"},
    "authority": {"emoji": "...", "text": "..."},
    "need": {"emoji": "...", "text": "..."},
    "timeline": {"emoji": "...", "text": "..."}
  },
  "steps": [{"titulo": "Step", "desc": "What to do", "chips": [{"text": "Topic", "key": true}], "key": true}]
}
"cliente": 3-5 items, "situacion": 3-4, "pains_secundarios": 2-4, "steps": exactly 5 (1-2 key:true), 2 chips per step.`,

  follow_up: `MEETING TYPE: FOLLOW-UP
Focus on base fields. "estado_deal" must summarize ALL previous meetings. "gaps" = topics not covered. "estrategia" = what to push for.
No additional fields needed.`,

  meddic_review: `MEETING TYPE: MEDDIC REVIEW
Include EXTRA fields:
{
  "meddic_status": {
    "metrics": {"emoji": "✅|⚠️|❌", "text": "Status + what's missing"},
    "economic_buyer": {"emoji": "...", "text": "..."},
    "decision_criteria": {"emoji": "...", "text": "..."},
    "decision_process": {"emoji": "...", "text": "..."},
    "identify_pain": {"emoji": "...", "text": "..."},
    "champion": {"emoji": "...", "text": "..."}
  },
  "preguntas_discovery": ["Question to validate gap 1", "Question 2"]
}
"preguntas_discovery": 3-5 items.`,

  pricing: `MEETING TYPE: PRICING
Include EXTRA fields:
{
  "roi_arguments": ["ROI argument with data"],
  "competitive": "Positioning vs competitors mentioned",
  "pricing_levers": ["Negotiation lever 1"],
  "pricing_risks": ["Price risk and mitigation"]
}
"roi_arguments": 2-4, "pricing_levers": 2-3, "pricing_risks": 1-3.`,

  closing: `MEETING TYPE: CLOSING
Include EXTRA fields:
{
  "blockers": [{"titulo": "Blocker", "detalle": "Cause and how to unblock", "prioridad": "alta|media"}],
  "buyer_signals": [{"signal": "Positive signal with evidence", "importancia": "alta|media|baja"}]
}
"blockers": 1-3 (alta first), "buyer_signals": 2-4 (alta first).`,

  ad_hoc: `MEETING TYPE: AD-HOC
General deal assessment. Focus on base fields only. No additional fields.`,
};

// ── Handler ───────────────────────────────────────────────────────────────

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, apikey",
      },
    });
  }

  try {
    const { deal_id, meeting_type: mt_override } = await req.json();
    if (!deal_id) return jsonResp({ error: "deal_id required" }, 400);

    // 1. Fetch deal
    const { data: deal, error: dealErr } = await sb
      .from("deals")
      .select("*, atlas:atlas_id(company_name)")
      .eq("id", deal_id)
      .maybeSingle();

    if (dealErr || !deal) return jsonResp({ error: "Deal not found" }, 404);

    const meetingType = mt_override || STAGE_TO_TYPE[deal.deal_stage] || "follow_up";
    const dealName = deal.deal_name || "?";

    // 2. Insert briefing row as 'generating'
    const { data: row, error: insErr } = await sb
      .from("briefings")
      .insert({
        deal_id,
        deal_name: dealName,
        meeting_type: meetingType,
        status: "generating",
      })
      .select("id")
      .single();

    if (insErr) return jsonResp({ error: "Insert failed: " + insErr.message }, 500);
    const briefingId = row.id;

    // 3. Build context
    const context = deal.deal_context || "";
    const atlas = deal.atlas as { company_name?: string } | null;
    const company = atlas?.company_name || dealName;
    const contextText = [
      `## DEAL — ${dealName}`,
      `Amount: ${deal.amount || "?"} | Stage: ${deal.deal_stage || "?"}`,
      `PBD: ${deal.pbd || "?"} | PAE: ${deal.pae || "?"}`,
      `Contacts: ${deal.contacts_info || "N/A"}`,
      "",
      context,
    ].join("\n");

    // 4. Call Claude via Azure
    const systemPrompt = BASE_PROMPT + "\n\n" + (TYPE_PROMPTS[meetingType] || TYPE_PROMPTS.ad_hoc);
    const userPrompt = `Generate briefing for: ${company}\nMeeting type: ${meetingType}\n\n${contextText}`;

    const baseUrl = AZURE_ENDPOINT.replace(/\/+$/, "");
    const claudeResp = await fetch(`${baseUrl}/v1/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": AZURE_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 16000,
        system: systemPrompt,
        messages: [{ role: "user", content: userPrompt }],
      }),
    });

    if (!claudeResp.ok) {
      const err = await claudeResp.text();
      await sb.from("briefings").update({ status: "error" }).eq("id", briefingId);
      return jsonResp({ error: "Claude error: " + err }, 502);
    }

    const claudeData = await claudeResp.json();
    const rawText = claudeData.content?.[0]?.text || "";
    const cleaned = rawText.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "").trim();
    const brief = JSON.parse(cleaned);

    // 5. Save result
    await sb.from("briefings").update({ brief, status: "ready" }).eq("id", briefingId);

    return jsonResp({ id: briefingId, status: "ready", brief });
  } catch (e) {
    return jsonResp({ error: String(e) }, 500);
  }
});

function jsonResp(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}
