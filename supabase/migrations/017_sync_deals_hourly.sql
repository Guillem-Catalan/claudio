-- Change sync_deals from daily (06:00 UTC) to hourly
-- Note: sync_deals_daily was already deleted, so no unschedule needed

SELECT cron.schedule(
  'sync_deals_hourly',
  '0 * * * *',
  'SELECT dispatch_sync_deals()'
);
