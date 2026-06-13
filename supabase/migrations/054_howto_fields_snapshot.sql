-- Add howto_label + howto_body to front_deal_snapshots
-- howto_label: short context phrase (~5 words) e.g. "Reactivar tras demo cancelada"
-- howto_body: 1-2 sentence approach e.g. "Apóyate en el leverage de Santander..."

ALTER TABLE front_deal_snapshots
  ADD COLUMN IF NOT EXISTS howto_label TEXT,
  ADD COLUMN IF NOT EXISTS howto_body TEXT;
