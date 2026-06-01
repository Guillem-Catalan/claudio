CREATE TABLE IF NOT EXISTS users (
  id UUID REFERENCES auth.users(id) PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  team TEXT NOT NULL DEFAULT 'Partners',
  subteam TEXT NOT NULL,
  role TEXT NOT NULL,
  reports_to UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  last_login TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read all users" ON users
  FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "Users can update own last_login" ON users
  FOR UPDATE USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can insert own row" ON users
  FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "Admin full access" ON users
  FOR ALL USING (
    auth.jwt() ->> 'email' = 'guillem.catalan@factorial.co'
  );
