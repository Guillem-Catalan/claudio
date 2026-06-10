import { createFileRoute } from "@tanstack/react-router";
import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import { convertToModelMessages, streamText, tool, stepCountIs } from "ai";
import { z } from "zod";
import { createClient } from "@supabase/supabase-js";

import { CLOSZR_SYSTEM_PROMPT } from "@/lib/closzr/system-prompt";
import { assertReadOnlySql } from "@/lib/closzr/sql-guard";

const SUPABASE_URL = "https://bqoepgcdgqylobkmqdur.supabase.co";
const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJxb2VwZ2NkZ3F5bG9ia21xZHVyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNTUyMzQsImV4cCI6MjA5MzgzMTIzNH0.FXajdSSsz6BgX9RJ_UVgy7q_9cavJdQWP1PHX9_zVhk";

export const Route = createFileRoute("/api/closzr")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const apiKey = process.env.LOVABLE_API_KEY;
        if (!apiKey) {
          return new Response("Missing LOVABLE_API_KEY", { status: 500 });
        }

        const { messages } = (await request.json()) as { messages: unknown };

        const gateway = createOpenAICompatible({
          name: "lovable",
          baseURL: "https://ai.gateway.lovable.dev/v1",
          headers: {
            "Lovable-API-Key": apiKey,
            "X-Lovable-AIG-SDK": "vercel-ai-sdk",
          },
        });

        const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
          auth: { persistSession: false, autoRefreshToken: false },
        });

        const runSql = tool({
          description:
            "Ejecuta una query SELECT/WITH de solo lectura sobre la base de datos de Factorial. Devuelve hasta 500 filas en JSON. Usa nombres de columna exactos.",
          inputSchema: z.object({
            query: z
              .string()
              .min(1)
              .describe("Sentencia SQL SELECT o WITH. Sin punto y coma final. Añade LIMIT cuando proceda."),
          }),
          execute: async ({ query }) => {
            console.log("[closzr] run_sql query:", query);
            try {
              const safe = assertReadOnlySql(query);
              const { data, error } = await sb.rpc("closzr_query", {
                query_text: safe,
              });
              if (error) {
                console.error("[closzr] rpc error:", error.message);
                return { error: error.message, hint: "La RPC closzr_query falló. Comunica al usuario el error literal." };
              }
              const rows = Array.isArray(data) ? data : [];
              console.log("[closzr] row_count:", rows.length);
              return {
                row_count: rows.length,
                truncated: rows.length > 500,
                rows: rows.slice(0, 500),
              };
            } catch (e) {
              const msg = e instanceof Error ? e.message : String(e);
              console.error("[closzr] tool error:", msg);
              return { error: msg };
            }
          },

        });

        const modelMessages = await convertToModelMessages(messages as never);

        const result = streamText({
          model: gateway("google/gemini-3-flash-preview"),
          system: CLOSZR_SYSTEM_PROMPT,
          messages: modelMessages,
          tools: { run_sql: runSql },
          stopWhen: stepCountIs(50),
        });

        return result.toUIMessageStreamResponse();
      },
    },
  },
});
