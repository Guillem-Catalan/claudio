import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const AZURE_ENDPOINT = Deno.env.get("AZURE_CLAUDE_ENDPOINT")!;
const AZURE_KEY = Deno.env.get("AZURE_CLAUDE_API_KEY")!;
const MODEL = Deno.env.get("AZURE_CLAUDE_FAST_DEPLOYMENT") || "claude-sonnet-4-6";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

const STAGE_CONTEXT: Record<string, string> = {
  "Demo Booked": "post-qualification, before first demo",
  "Meeting Booked": "post-qualification, before first demo",
  "Meeting scheduled": "post-qualification, before first demo",
  "Product Alignment": "post-demo, product alignment phase",
  "Discovery": "discovery phase, gathering requirements",
  "MEDDPICC Criteria Validation": "MEDDIC validation, mid-funnel",
  "Economical Allignment": "pricing/negotiation phase",
  "Pricing and Packaging": "pricing/negotiation phase",
  "Contract Sent": "closing phase, contract under review",
};

const SYSTEM_PROMPT = `You are CLAUDIO — an automated Sales Team Lead for Factorial's Strategic Partnerships channel.

You will receive the full context of a deal. Generate a follow-up email that the PAE (Account Executive) will send to the prospect.

OUTPUT — return a single JSON object:

{
  "recipient": "Name — Job Title (who should receive this email)",
  "send_when": "When to send it (e.g. 'Mañana a primera hora', 'Hoy antes de las 18h', 'Lunes tras el fin de semana')",
  "reason": "Why this email now — one sentence explaining the purpose",
  "subject": "Email subject line — short, specific, professional",
  "body": "Full email body ready to send. Include greeting, content, and sign-off. Use line breaks."
}

RULES:
- Language: Spanish
- The email is FROM the PAE TO the prospect — write it as a real sales email
- Professional but warm tone. Not robotic, not overly casual.
- Reference specific things discussed (calls, demos, meetings) from the context
- Include a clear call to action (next meeting, decision, feedback request)
- Keep it concise — 4-8 sentences max in the body
- Sign off with just the PAE's first name (extract from deal context)
- "recipient": identify the best contact from the deal to send to. Use name + job title.
- "send_when": be specific based on the deal timing/urgency
- "reason": one clear sentence the PAE reads to understand why they should send this now
- Never invent meetings or conversations not in the context
- Return ONLY the JSON. No markdown fences.`;

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
    const { deal_id } = await req.json();
    if (!deal_id) return jsonResp({ error: "deal_id required" }, 400);

    const { data: deal, error: dealErr } = await sb
      .from("deals")
      .select("*, atlas:atlas_id(company_name)")
      .eq("id", deal_id)
      .maybeSingle();

    if (dealErr || !deal) return jsonResp({ error: "Deal not found" }, 404);

    const dealName = deal.deal_name || "?";
    const context = deal.deal_context || "";
    const atlas = deal.atlas as { company_name?: string } | null;
    const company = atlas?.company_name || dealName;
    const stageHint = STAGE_CONTEXT[deal.deal_stage] || "active deal";

    const contextText = [
      `## DEAL — ${dealName}`,
      `Amount: ${deal.amount || "?"} | Stage: ${deal.deal_stage || "?"} (${stageHint})`,
      `PBD: ${deal.pbd || "?"} | PAE: ${deal.pae || "?"}`,
      `Contacts: ${deal.contacts_info || "N/A"}`,
      "",
      context,
    ].join("\n");

    const userPrompt = `Generate follow-up email for: ${company}\nDeal stage: ${deal.deal_stage || "unknown"}\n\n${contextText}`;

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
        max_tokens: 4000,
        system: SYSTEM_PROMPT,
        messages: [{ role: "user", content: userPrompt }],
      }),
    });

    if (!claudeResp.ok) {
      const err = await claudeResp.text();
      return jsonResp({ error: "Claude error: " + err }, 502);
    }

    const claudeData = await claudeResp.json();
    const rawText = claudeData.content?.[0]?.text || "";
    const cleaned = rawText.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "").trim();
    const email = JSON.parse(cleaned);

    const { data: row, error: insErr } = await sb
      .from("email_drafts")
      .insert({
        deal_id,
        deal_name: dealName,
        recipient: email.recipient,
        send_when: email.send_when,
        reason: email.reason,
        subject: email.subject,
        body: email.body,
        status: "draft",
        context_snapshot_at: deal.updated_at || new Date().toISOString(),
      })
      .select("id")
      .single();

    if (insErr) return jsonResp({ error: "Insert failed: " + insErr.message }, 500);

    return jsonResp({ id: row.id, ...email });
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
