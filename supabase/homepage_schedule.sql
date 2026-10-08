-- Apply after homepage-refresh is deployed with custom token authentication.
-- Replaces only this job; existing social publishing and reports stay intact.
select cron.unschedule(jobid) from cron.job where jobname='homepage-price-refresh';
select cron.schedule('homepage-price-refresh','*/5 * * * *',$job$
 select net.http_post(
  url:='https://cmexmobjpeavlppmffqi.supabase.co/functions/v1/homepage-refresh',
  headers:=jsonb_build_object('Content-Type','application/json','x-publication-queue-token',
   (select decrypted_secret from vault.decrypted_secrets where name='publication_queue_token')),
  body:='{}'::jsonb,timeout_milliseconds:=100000
 );
$job$);
