-- Preserve historical requests; absent browser metadata is not evidence of a person.
alter table public.deal_click_events
  add column request_kind text not null default 'unverified'
    check (request_kind in ('navigation','unverified','bot','prefetch')),
  add column request_purpose text,
  add column fetch_mode text,
  add column fetch_dest text,
  add column fetch_user text;

create or replace function public.get_click_report_v2(
  p_days integer, p_complete_days boolean default false,
  p_as_of timestamptz default now()
) returns jsonb language plpgsql security definer set search_path = ''
as $function$
declare
  v_days integer := greatest(1, least(coalesce(p_days, 7), 90));
  v_end timestamptz := coalesce(p_as_of, now());
  v_start timestamptz;
  v_rows jsonb;
  v_bots bigint;
begin
  if p_complete_days then
    v_end := date_trunc('day', v_end at time zone 'Europe/Istanbul') at time zone 'Europe/Istanbul';
  end if;
  v_start := v_end - make_interval(days => v_days);
  select count(*) into v_bots from public.deal_click_events e
    where e.clicked_at >= v_start and e.clicked_at < v_end
      and (e.is_bot or e.request_kind in ('bot','prefetch'));

  with eligible as (
    select e.*,
      coalesce(nullif(e.visitor_hash, ''), md5(coalesce(e.user_agent, '') || '|' || coalesce(e.referer, ''))) visitor_key,
      (e.clicked_at at time zone 'Europe/Istanbul')::date local_day
    from public.deal_click_events e
    where e.clicked_at >= v_start and e.clicked_at < v_end
      and not e.is_bot and e.request_kind in ('navigation','unverified')
      and (e.request_kind = 'navigation' or not exists (
        select 1 from public.deal_publications p
        where p.deal_candidate_id = e.deal_candidate_id and p.platform = e.channel
          and p.published_at is not null
          and e.clicked_at >= p.published_at
          and e.clicked_at < p.published_at + interval '15 seconds'
      ))
  ), deduplicated as (
    select distinct on (e.local_day, e.deal_candidate_id, e.channel, e.visitor_key)
      e.deal_candidate_id, e.merchant_id, e.channel, e.request_kind
    from eligible e
    order by e.local_day, e.deal_candidate_id, e.channel, e.visitor_key,
      (e.request_kind = 'navigation') desc, e.clicked_at
  ), grouped as (
    select e.channel, m.name merchant, cp.title,
      count(*) filter (where e.request_kind = 'navigation') clicks,
      count(*) filter (where e.request_kind = 'unverified') unverified_clicks
    from deduplicated e
    join public.deal_candidates dc on dc.id = e.deal_candidate_id
    join public.canonical_products cp on cp.id = dc.canonical_product_id
    join public.merchants m on m.id = e.merchant_id
    group by e.channel, m.name, cp.title
  )
  select coalesce(jsonb_agg(to_jsonb(g) order by g.clicks desc, g.unverified_clicks desc, g.title), '[]'::jsonb)
    into v_rows from grouped g;
  return jsonb_build_object('period_start',v_start,'period_end',v_end,
    'rows',v_rows,'bot_requests',v_bots,'metric','browser_navigation_per_product_channel_day');
end;
$function$;
revoke all on function public.get_click_report_v2(integer,boolean,timestamptz) from public,anon,authenticated;
grant execute on function public.get_click_report_v2(integer,boolean,timestamptz) to service_role;

-- Older consumers must not resume calling unverified requests "human clicks".
create or replace function public.get_click_report(p_days integer,p_complete_days boolean default false)
returns table(channel text,merchant text,title text,clicks bigint)
language sql security definer set search_path = ''
as $function$
  select r.channel,r.merchant,r.title,r.clicks
  from jsonb_to_recordset(public.get_click_report_v2(p_days,p_complete_days)->'rows')
    as r(channel text,merchant text,title text,clicks bigint,unverified_clicks bigint)
  where r.clicks > 0;
$function$;
revoke all on function public.get_click_report(integer,boolean) from public,anon,authenticated;
grant execute on function public.get_click_report(integer,boolean) to service_role;
