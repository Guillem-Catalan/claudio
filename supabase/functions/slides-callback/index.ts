import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const EXPECTED_API_KEY = "EwMunUjVSTucXumtyIbZfhXzL1wIT9ek";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-api-key",
      },
    });
  }

  // Auth check
  const apiKey = req.headers.get("x-api-key");
  if (apiKey !== EXPECTED_API_KEY) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
  }

  try {
    const body = await req.json();
    const { slide_id, presentation_url, deal_id } = body;

    if (!presentation_url) {
      return new Response(JSON.stringify({ error: "presentation_url required" }), { status: 400 });
    }

    // Update by slide_id if provided
    if (slide_id) {
      const { error } = await sb
        .from("slides")
        .update({
          status: "ready",
          presentation_url: presentation_url,
          updated_at: new Date().toISOString(),
        })
        .eq("id", slide_id);

      if (error) {
        return new Response(JSON.stringify({ error: "Update failed", detail: error }), { status: 500 });
      }

      return new Response(JSON.stringify({ ok: true, slide_id }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Fallback: update by deal_id (latest pending)
    if (deal_id) {
      const { data: pending } = await sb
        .from("slides")
        .select("id")
        .eq("deal_id", deal_id)
        .eq("status", "pending")
        .order("created_at", { ascending: false })
        .limit(1);

      if (pending && pending.length > 0) {
        await sb
          .from("slides")
          .update({
            status: "ready",
            presentation_url: presentation_url,
            updated_at: new Date().toISOString(),
          })
          .eq("id", pending[0].id);

        return new Response(JSON.stringify({ ok: true, slide_id: pending[0].id }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
    }

    return new Response(JSON.stringify({ error: "No matching slide found. Provide slide_id or deal_id." }), { status: 404 });
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
  }
});
