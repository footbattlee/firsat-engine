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
  with eligible as (
    select
      e.*,
      coalesce(
        nullif(e.visitor_hash, ''),
        md5(coalesce(e.user_agent, '') || '|' || coalesce(e.referer, ''))
      ) as visitor_key,
      (e.clicked_at at time zone 'Europe/Istanbul')::date as local_day
    from public.deal_click_events e
    where not e.is_bot
      and e.clicked_at >= v_start
      and e.clicked_at < v_end
      and not exists (
        select 1
        from public.deal_publications p
        where p.deal_candidate_id = e.deal_candidate_id
          and p.platform = e.channel
          and p.published_at is not null
          and e.clicked_at >= p.published_at
          and e.clicked_at < p.published_at + interval '15 seconds'
      )
  ),
  unique_clicks as (
    select distinct on (e.local_day, e.deal_candidate_id, e.channel, e.visitor_key)
      e.deal_candidate_id,
      e.merchant_id,
      e.channel
    from eligible e
    order by e.local_day, e.deal_candidate_id, e.channel, e.visitor_key, e.clicked_at
  )
  select
    e.channel,
    m.name,
    cp.title,
    count(*)::bigint
  from unique_clicks e
  join public.deal_candidates dc on dc.id = e.deal_candidate_id
  join public.canonical_products cp on cp.id = dc.canonical_product_id
  join public.merchants m on m.id = e.merchant_id
  group by e.channel, m.name, cp.title
  order by count(*) desc, cp.title;
end;
$function$;

revoke all on function public.get_click_report(integer, boolean) from public, anon, authenticated;
grant execute on function public.get_click_report(integer, boolean) to service_role;
