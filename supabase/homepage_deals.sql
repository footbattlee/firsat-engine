-- Website snapshots never alter social publication queues.
create table if not exists public.homepage_manual_deals (
 id uuid primary key default gen_random_uuid(), title text not null, brand text not null default '',
 merchant_slug text not null check(merchant_slug in ('amazon','trendyol','hepsiburada','n11','mediamarkt','vatan')),
 product_url text not null check(product_url like 'https://%'),
 affiliate_url text not null check(affiliate_url like 'https://%'), image_url text,
 active boolean not null default true, expires_at timestamptz not null,
 created_at timestamptz not null default now()
);
create table if not exists public.homepage_deals (
 id text primary key, candidate_id uuid references public.deal_candidates(id) on delete cascade,
 manual_id uuid references public.homepage_manual_deals(id) on delete cascade,
 offer_id uuid references public.offers(id) on delete cascade,
 title text not null, brand text not null default '', merchant_slug text not null,
 merchant_name text not null, product_url text not null, affiliate_url text,
 image_url text, price numeric, competitor_price numeric, competitor_name text,
 status text not null default 'unverified' check(status in ('verified','unverified','ended')),
 checked_at timestamptz, attempted_at timestamptz not null default now(),
 expires_at timestamptz, error_code text,
 check(price is null or price>0), check(competitor_price is null or competitor_price>0),
 check((candidate_id is not null)::int+(manual_id is not null)::int=1)
);
create index if not exists homepage_deals_status_checked_idx on public.homepage_deals(status,checked_at);
alter table public.homepage_deals enable row level security;
alter table public.homepage_manual_deals enable row level security;
revoke all on public.homepage_deals,public.homepage_manual_deals from anon,authenticated;
grant all on public.homepage_deals,public.homepage_manual_deals to service_role;
