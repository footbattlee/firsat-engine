-- Server-only anonymous daily counters. No raw IP, full referrer or cookie stored.
create table public.site_traffic_events (
 event_key text primary key check (event_key ~ '^[a-f0-9]{64}$'),
 event_type text not null check (event_type in ('pageview','outbound')),
 path text not null check (length(path) <= 100),
 listing_id text, merchant text,
 visitor_hash text not null check (visitor_hash ~ '^[a-f0-9]{64}$'),
 request_kind text not null check (request_kind in ('client_view','navigation','unverified','bot','prefetch')),
 occurred_at timestamptz not null default now()
);
create index site_traffic_events_time_idx on public.site_traffic_events(occurred_at);
alter table public.site_traffic_events enable row level security;
revoke all on public.site_traffic_events from anon,authenticated;
grant select,insert on public.site_traffic_events to service_role;
create or replace function public.get_click_report_v3(
 p_days integer,p_complete_days boolean default false,p_as_of timestamptz default now()
) returns jsonb language plpgsql security definer set search_path = ''
as $function$
declare
 r jsonb := public.get_click_report_v2(p_days,p_complete_days,p_as_of);
 v_start timestamptz := (r->>'period_start')::timestamptz;
 v_end timestamptz := (r->>'period_end')::timestamptz;
 site jsonb;
begin
 with dedup as (
  select distinct on ((occurred_at at time zone 'Europe/Istanbul')::date,event_type,path,visitor_hash)
   event_type,request_kind,merchant
  from public.site_traffic_events
  where occurred_at >= v_start and occurred_at < v_end
   and request_kind not in ('bot','prefetch')
  order by (occurred_at at time zone 'Europe/Istanbul')::date,event_type,path,visitor_hash,
   (request_kind in ('client_view','navigation')) desc,occurred_at
 )
 select jsonb_build_object(
  'page_views',count(*) filter(where event_type='pageview' and request_kind='client_view'),
  'outbound_clicks',count(*) filter(where event_type='outbound' and request_kind='navigation'),
  'unverified_outbound',count(*) filter(where event_type='outbound' and request_kind='unverified')
 ) into site from dedup;
 return r || jsonb_build_object('website',site,'website_domain','fırsatcı.com');
end;
$function$;
revoke all on function public.get_click_report_v3(integer,boolean,timestamptz) from public,anon,authenticated;
grant execute on function public.get_click_report_v3(integer,boolean,timestamptz) to service_role;

-- A current purchase price can be shown without inventing a competitor discount.
alter table public.homepage_deals add column price_checked_at timestamptz;
