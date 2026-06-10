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

  const apiKey = req.headers.get("x-api-key");
  if (apiKey !== EXPECTED_API_KEY) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
  }

  try {
    const body = await req.json();
    const {
      callback_slide_id,
      slide_id: legacySlideId,
      status: cbStatus,
      share_url,
      html_slides,
      slide_images,
      presentation_url: legacyUrl,
      error_message,
      deal_id,
    } = body;

    const slideId = callback_slide_id || legacySlideId;
    const url = share_url || legacyUrl;
    const finalStatus = cbStatus === "completed" || cbStatus === "ready" ? "ready" : cbStatus === "failed" ? "error" : "ready";

    const updateData: Record<string, unknown> = {
      status: finalStatus,
      updated_at: new Date().toISOString(),
    };
    if (url) updateData.share_url = url;
    if (url) updateData.presentation_url = url;
    if (html_slides) updateData.html_slides = html_slides;
    if (slide_images) updateData.slide_images = slide_images;

    if (slideId) {
      const { error } = await sb.from("slides").update(updateData).eq("id", slideId);
      if (error) {
        return new Response(JSON.stringify({ error: "Update failed", detail: error }), { status: 500 });
      }
      return new Response(JSON.stringify({ ok: true, slide_id: slideId }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (deal_id) {
      const { data: pending } = await sb
        .from("slides")
        .select("id")
        .eq("deal_id", deal_id)
        .eq("status", "pending")
        .order("created_at", { ascending: false })
        .limit(1);

      if (pending && pending.length > 0) {
        await sb.from("slides").update(updateData).eq("id", pending[0].id);
        return new Response(JSON.stringify({ ok: true, slide_id: pending[0].id }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
    }

    return new Response(JSON.stringify({ error: "No matching slide found" }), { status: 404 });
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
  }
});
