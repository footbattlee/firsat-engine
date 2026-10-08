do $block$
declare j record;
begin
 for j in select jobid,jobname from cron.job where jobname in ('click-report-daily','click-report-weekly') loop
  perform cron.alter_job(j.jobid,command:=format($command$
   select net.http_post(
    url:='https://cmexmobjpeavlppmffqi.supabase.co/functions/v1/click-report',
    headers:=jsonb_build_object('Content-Type','application/json','x-publication-queue-token',
      (select decrypted_secret from vault.decrypted_secrets where name='publication_queue_token' limit 1)),
    body:=jsonb_build_object('schedule',%L)
   );
  $command$,case when j.jobname='click-report-daily' then 'daily' else 'weekly' end));
 end loop;
end;
$block$;