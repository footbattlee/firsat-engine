do $block$
declare job record;
begin
  for job in select jobid from cron.job where jobname='instagram-publication-half-hour'
  loop perform cron.unschedule(job.jobid); end loop;
end $block$;
select cron.schedule(
 'instagram-publication-half-hour',
 '0,30 7-20 * * *',
 $job$select net.http_post(
   url := 'https://cmexmobjpeavlppmffqi.supabase.co/functions/v1/publication-queue',
   headers := jsonb_build_object('Content-Type','application/json',
      'x-publication-queue-token',(select decrypted_secret from vault.decrypted_secrets where name='publication_queue_token')),
   body := '{}'::jsonb,
   timeout_milliseconds := 120000
 );$job$
);
update public.publication_queue_settings set enabled=true where id=true;
