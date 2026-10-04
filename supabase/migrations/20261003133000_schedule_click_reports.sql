create extension if not exists pg_cron with schema extensions;
create extension if not exists pg_net with schema extensions;

create table if not exists public.click_report_dispatches (
  period_key text primary key,
  report_type text not null check (report_type in ('daily','weekly')),
  status text not null check (status in ('sending','sent','failed')),
  sent_at timestamptz,
  error_message text,
  updated_at timestamptz not null default now()
);

alter table public.click_report_dispatches enable row level security;

create or replace function public.get_click_report(
  p_days integer,
  p_complete_days boolean default false
)
returns table (
  channel text,
  merchant text,
  title text,
  clicks bigint
)
language plpgsql
security definer
set search_path = public
as $function$
declare
  v_days integer := greatest(1, least(coalesce(p_days, 7), 90));
  v_end timestamptz;
  v_start timestamptz;
begin
  if p_complete_days then
    v_end := date_trunc('day', now() at time zone 'Europe/Istanbul') at time zone 'Europe/Istanbul';
  else
    v_end := now();
  end if;
  v_start := v_end - make_interval(days => v_days);

  return query
  select
    e.channel,
    m.name,
    cp.title,
    count(*)::bigint
  from public.deal_click_events e
  join public.deal_candidates dc on dc.id = e.deal_candidate_id
  join public.canonical_products cp on cp.id = dc.canonical_product_id
  join public.merchants m on m.id = e.merchant_id
  where not e.is_bot
    and e.clicked_at >= v_start
    and e.clicked_at < v_end
  group by e.channel, m.name, cp.title
  order by count(*) desc, cp.title;
end;
$function$;

revoke all on function public.get_click_report(integer, boolean) from public, anon, authenticated;
grant execute on function public.get_click_report(integer, boolean) to service_role;

do $block$
declare job record;
begin
  for job in select jobid from cron.job where jobname in ('click-report-daily','click-report-weekly')
  loop
    perform cron.unschedule(job.jobid);
  end loop;
end
$block$;

select cron.schedule(
  'click-report-daily',
  '1,3,5 21 * * *',
  $job$select net.http_post(
    url := 'https://cmexmobjpeavlppmffqi.supabase.co/functions/v1/click-report',
    headers := '{"Content-Type":"application/json"}'::jsonb,
    body := '{"schedule":"daily"}'::jsonb
  );$job$
);

select cron.schedule(
  'click-report-weekly',
  '0,2,4 5 * * 0',
  $job$select net.http_post(
    url := 'https://cmexmobjpeavlppmffqi.supabase.co/functions/v1/click-report',
    headers := '{"Content-Type":"application/json"}'::jsonb,
    body := '{"schedule":"weekly"}'::jsonb
  );$job$
);
