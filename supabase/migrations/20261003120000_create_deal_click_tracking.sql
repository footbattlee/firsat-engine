create table if not exists public.deal_click_events (
  id bigint generated always as identity primary key,
  deal_candidate_id uuid not null references public.deal_candidates(id) on delete cascade,
  offer_id uuid not null references public.offers(id) on delete cascade,
  merchant_id uuid not null references public.merchants(id),
  channel text not null default 'other'
    check (channel in ('telegram','facebook','instagram','whatsapp','other')),
  is_bot boolean not null default false,
  user_agent text,
  referer text,
  clicked_at timestamptz not null default now()
);

alter table public.deal_click_events enable row level security;

create index if not exists deal_click_events_clicked_at_idx
  on public.deal_click_events (clicked_at desc);
create index if not exists deal_click_events_candidate_idx
  on public.deal_click_events (deal_candidate_id, clicked_at desc);
create index if not exists deal_click_events_merchant_idx
  on public.deal_click_events (merchant_id, clicked_at desc);

create or replace view public.deal_click_summary
with (security_invoker = true)
as
select
  e.clicked_at::date as clicked_on,
  e.deal_candidate_id,
  dc.canonical_product_id,
  cp.title,
  e.offer_id,
  e.merchant_id,
  m.name as merchant,
  e.channel,
  count(*) filter (where not e.is_bot) as clicks,
  count(*) filter (where e.is_bot) as bot_clicks
from public.deal_click_events e
join public.deal_candidates dc on dc.id = e.deal_candidate_id
join public.canonical_products cp on cp.id = dc.canonical_product_id
join public.merchants m on m.id = e.merchant_id
group by
  e.clicked_at::date, e.deal_candidate_id, dc.canonical_product_id,
  cp.title, e.offer_id, e.merchant_id, m.name, e.channel;
