import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const AZURE_ENDPOINT = Deno.env.get("AZURE_CLAUDE_ENDPOINT")!;
const AZURE_KEY = Deno.env.get("AZURE_CLAUDE_API_KEY")!;
const MODEL = Deno.env.get("AZURE_CLAUDE_FAST_DEPLOYMENT") || "claude-sonnet-4-6";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

const SYSTEM_PROMPT = `You are CLAUDIO — an automated Sales Team Lead for Factorial's Strategic Partnerships channel.

You will receive the full context of a deal, today's meeting details (if any), and the latest deal assessment. Generate a follow-up email that the PAE (Account Executive) will send to the prospect.

MEETING OUTCOMES — adapt the email to what happened:
- COMPLETED: The meeting happened. Reference what was discussed, propose clear next steps.
- NO_SHOW: The prospect didn't show up. Polite, assume they were busy. Propose 2-3 alternative time slots. Don't guilt-trip.
- CANCELED / RESCHEDULED: Meeting was canceled or moved. Acknowledge it, propose new times if no reschedule exists.
- SCHEDULED (future): Meeting is coming up. Send a confirmation/reminder with agenda preview.
- No meeting data: Generic follow-up based on deal stage and last activity.

OUTPUT — return a single JSON object:

{
  "recipient": "Name — Job Title (who should receive this email)",
  "send_when": "When to send (e.g. 'Hoy antes de las 18h', 'Mañana a primera hora')",
  "reason": "Why this email now — one sentence explaining the strategic purpose",
  "subject": "Email subject line — short, specific, professional",
  "body": "Full email body ready to send. Use \\n for line breaks."
}

RULES:
- Language: Spanish
- The email is FROM the PAE TO the prospect — write it as a real sales email
- Professional but warm tone. Not robotic, not overly casual.
- Reference SPECIFIC things from the context: names, topics discussed, products mentioned, pain points, numbers
- For COMPLETED meetings: summarize key takeaways, attach next steps, propose specific follow-up date
- For NO_SHOW: be empathetic ("entiendo que surgen imprevistos"), propose 2-3 specific time slots in the next 3-5 business days
- For first demos: highlight key value propositions that resonated, reference their specific pain points
- For pricing/closing stages: be more direct, reference commercial terms, push for decision timeline
- Include a clear, specific call to action (not vague "let's talk")
- Keep it concise — 4-8 sentences max in the body
- Sign off with just the PAE's first name (extract from deal context)
- "recipient": identify the best contact from the deal to send to. Use name + job title if available.
- "send_when": be specific based on urgency. NO_SHOW = today. COMPLETED = next business day morning. SCHEDULED = day before.
- Never invent meetings, conversations, or details not in the context
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

    // 1. Fetch deal with atlas
    const { data: deal, error: dealErr } = await sb
      .from("deals")
      .select("*, atlas:atlas_id(company_name, company_size, industry)")
      .eq("id", deal_id)
      .maybeSingle();

    if (dealErr || !deal) return jsonResp({ error: "Deal not found" }, 404);

    // 2. Fetch today's meetings for this deal
    const today = new Date().toISOString().slice(0, 10);
    const { data: todayMeetings } = await sb
      .from("deal_meetings")
      .select("title, meeting_start, outcome")
      .eq("deal_id", deal_id)
      .gte("meeting_start", today + "T00:00:00Z")
      .lte("meeting_start", today + "T23:59:59Z")
      .order("meeting_start", { ascending: false });

    // 3. Fetch latest snapshot for deal assessment
    const { data: snapshots } = await sb
      .from("front_deal_snapshots")
      .select("deal_summary, deal_assessment, buyer_signals, live_blockers, next_step, close_probability, claudio_forecast")
      .eq("deal_id", deal_id)
      .order("snapshot_date", { ascending: false })
      .limit(1);

    const snap = snapshots?.[0] || null;
    const atlas = deal.atlas as { company_name?: string; company_size?: string; industry?: string } | null;
    const company = atlas?.company_name || deal.deal_name || "?";

    // 4. Build rich context for Claude
    const meetingInfo = todayMeetings?.length
      ? todayMeetings.map((m: { title?: string; meeting_start?: string; outcome?: string }) => {
          const time = m.meeting_start ? m.meeting_start.slice(11, 16) : "?";
          return `- ${time} | "${m.title || "Sin título"}" | Outcome: ${m.outcome || "UNKNOWN"}`;
        }).join("\n")
      : "No meetings today.";

    const snapInfo = snap
      ? [
          snap.deal_assessment ? `Assessment: ${snap.deal_assessment}` : "",
          snap.buyer_signals ? `Buyer signals: ${snap.buyer_signals}` : "",
          snap.live_blockers ? `Blockers: ${snap.live_blockers}` : "",
          snap.next_step ? `Recommended next step: ${snap.next_step}` : "",
          snap.close_probability != null ? `Close probability: ${snap.close_probability}%` : "",
          snap.claudio_forecast ? `Forecast: ${snap.claudio_forecast}` : "",
        ].filter(Boolean).join("\n")
      : "No snapshot available.";

    const contextText = [
      `## DEAL — ${deal.deal_name || "?"}`,
      `Company: ${company}${atlas?.company_size ? " | Size: " + atlas.company_size : ""}${atlas?.industry ? " | Industry: " + atlas.industry : ""}`,
      `Amount: ${deal.amount || "?"} | Stage: ${deal.deal_stage || "?"}`,
      `PBD: ${deal.pbd || "?"} | PAE: ${deal.pae || "?"}`,
      `Contacts: ${deal.contacts_info || "N/A"}`,
      "",
      "## TODAY'S MEETINGS",
      meetingInfo,
      "",
      "## LATEST DEAL ASSESSMENT",
      snapInfo,
      "",
      "## FULL DEAL HISTORY",
      deal.deal_context || "No context available.",
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
        deal_name: deal.deal_name,
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
