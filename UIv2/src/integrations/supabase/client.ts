import { createClient } from "@supabase/supabase-js";

// External Supabase project (Factorial — Claudio Sales Intelligence).
// Anon key is publishable; safe in client code.
const SUPABASE_URL = "https://bqoepgcdgqylobkmqdur.supabase.co";
const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJxb2VwZ2NkZ3F5bG9ia21xZHVyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgyNTUyMzQsImV4cCI6MjA5MzgzMTIzNH0.FXajdSSsz6BgX9RJ_UVgy7q_9cavJdQWP1PHX9_zVhk";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

export const SUPABASE_FUNCTIONS_URL = `${SUPABASE_URL}/functions/v1`;
export const SUPABASE_PUBLISHABLE_KEY = SUPABASE_ANON_KEY;
