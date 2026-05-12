-- Restore missing cron jobs: pae_demo_prep_daily and sync_deals_daily
-- (modjo_fetch_every_30min already exists)

SELECT cron.schedule(
  'pae_demo_prep_daily',
  '0 7 * * *',
  'SELECT dispatch_pae_demo_prep()'
);

SELECT cron.schedule(
  'sync_deals_daily',
  '0 6 * * *',
  'SELECT dispatch_sync_deals()'
);
