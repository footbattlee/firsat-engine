
-- Per-offer purchase checks are separate from daily pipeline price history.
create table if not exists public.website_offer_checks (
 offer_id uuid primary key references public.offers(id) on delete cascade,
 product_url text not null, price numeric check(price>0), checked_at timestamptz,
 available boolean not null default false, attempted_at timestamptz not null, error_code text,
 check ((price is null)=(checked_at is null))
);
alter table public.website_offer_checks enable row level security;
revoke all on public.website_offer_checks from public,anon,authenticated;
grant select,insert,update,delete on public.website_offer_checks to service_role;

create or replace function public.website_save_offer_check(p_offer_id uuid,p_product_url text,p_observed_at timestamptz,p_price numeric default null,p_error text default null)
returns void language plpgsql security invoker set search_path='' as $$
declare temporary boolean;
begin
 if p_observed_at>now()+interval '5 seconds' or p_observed_at<now()-interval '1 hour' then raise exception 'invalid observation time'; end if;
 if not exists(select 1 from public.offers where id=p_offer_id and product_url=p_product_url) then raise exception 'offer URL changed'; end if;
 if p_price is not null and p_price<=0 then raise exception 'invalid price'; end if;
 temporary := coalesce(p_error,'') ~ '^(store-http-(403|429|5[0-9][0-9])|check-timeout|check-failed|.*timeout.*|.*timed out.*|.*fetch failed.*|.*network.*)$';
 insert into public.website_offer_checks as old(offer_id,product_url,price,checked_at,available,attempted_at,error_code)
 values(p_offer_id,p_product_url,p_price,case when p_price is not null then p_observed_at end,p_price is not null,p_observed_at,left(p_error,120))
 on conflict(offer_id) do update set
 product_url=excluded.product_url,
 price=case when old.product_url=excluded.product_url then coalesce(excluded.price,old.price) else excluded.price end,
 checked_at=case when old.product_url=excluded.product_url then coalesce(excluded.checked_at,old.checked_at) else excluded.checked_at end,
 available=excluded.available or (temporary and old.product_url=excluded.product_url and old.available),
 attempted_at=excluded.attempted_at,error_code=excluded.error_code
 where old.attempted_at<=excluded.attempted_at;
end $$;
revoke all on function public.website_save_offer_check(uuid,text,timestamptz,numeric,text) from public,anon,authenticated;
grant execute on function public.website_save_offer_check(uuid,text,timestamptz,numeric,text) to service_role;

-- Seed only actual successful checks, retaining their original time.
insert into public.website_offer_checks(offer_id,product_url,price,checked_at,available,attempted_at)
select distinct on(h.offer_id) h.offer_id,h.product_url,h.price,h.price_checked_at,true,h.price_checked_at
from public.homepage_deals h join public.offers o on o.id=h.offer_id and o.product_url=h.product_url
where h.status<>'ended' and h.price>0 and h.price_checked_at<=now()
order by h.offer_id,h.price_checked_at desc
on conflict(offer_id) do nothing;

create or replace function public.website_market_offers(p_listing_id text)
returns setof jsonb language sql stable security invoker set search_path='' set statement_timeout='5s' as $$
 select x || jsonb_build_object('live_price',case when c.available and not coalesce((x->>'in_stock')::boolean=false and (x->>'checked_at')::timestamptz>c.checked_at,false) then c.price end,
 'live_checked_at',case when c.available and not coalesce((x->>'in_stock')::boolean=false and (x->>'checked_at')::timestamptz>c.checked_at,false) then c.checked_at end,'last_error',c.error_code)
 from public.website_product_offers(p_listing_id) x
 left join public.website_offer_checks c on c.offer_id=(x->>'id')::uuid and c.product_url=x->>'product_url'
 order by case when c.available and not coalesce((x->>'in_stock')::boolean=false and (x->>'checked_at')::timestamptz>c.checked_at,false) and c.checked_at>now()-interval '6 hours' then 0 else 1 end,c.price nulls last,(x->>'price')::numeric nulls last,x->>'id'
$$;
revoke all on function public.website_market_offers(text) from public,anon,authenticated;
grant execute on function public.website_market_offers(text) to service_role;

create or replace function public.website_market_catalogue(p_listing_id text default null)
returns setof jsonb language sql stable security invoker set search_path='' set statement_timeout='10s' as $$
 with listings as materialized (select x from public.website_catalogue(p_listing_id) x),
 matched as materialized (
 select l.x->>'id' listing_id,jsonb_build_object('id',o.id,'merchant_slug',m.slug,'merchant_name',m.name,'price',o.price,'checked_at',o.last_checked_at,'in_stock',o.in_stock,'product_url',o.product_url,'affiliate_url',o.affiliate_url,
 'live_price',case when c.available and not coalesce(o.in_stock=false and o.last_checked_at>c.checked_at,false) then c.price end,
 'live_checked_at',case when c.available and not coalesce(o.in_stock=false and o.last_checked_at>c.checked_at,false) then c.checked_at end) x
 from listings l join public.offers ao on ao.id=(l.x->>'offer_id')::uuid
 join public.product_variants av on av.id=ao.product_variant_id
 join public.product_matches pm on pm.canonical_product_id=(l.x->>'canonical_product_id')::uuid and pm.status='approved'
 join public.products p on p.id=pm.product_id and p.active
 join public.product_variants v on v.product_id=p.id and v.active
 join public.offers o on o.product_variant_id=v.id and o.currency='TRY'
 join public.merchants m on m.id=o.merchant_id and m.active
 left join public.website_offer_checks c on c.offer_id=o.id and c.product_url=o.product_url
 where o.id=ao.id or ((av.gtin is null or v.gtin=av.gtin) and lower(coalesce(v.color,''))=lower(coalesce(av.color,'')) and lower(coalesce(v.size,''))=lower(coalesce(av.size,'')) and lower(coalesce(v.capacity,''))=lower(coalesce(av.capacity,'')))
 ),
 enriched as (
 select l.x,live.x live,recorded.x recorded,counts.n offer_count,rival.x rival,old.price old_price,old.checked_at old_checked_at
 from listings l
 left join lateral (
  select x from matched where listing_id=l.x->>'id'
  and (x->>'live_price')::numeric>0 and (x->>'live_checked_at')::timestamptz>now()-interval '6 hours'
  and (x->>'live_checked_at')::timestamptz<=now()
  order by (x->>'live_price')::numeric,(x->>'live_checked_at')::timestamptz desc,x->>'id' limit 1
 ) live on true
 left join lateral (
  select x from matched where listing_id=l.x->>'id'
  and (x->>'price')::numeric>0 and (x->>'in_stock')::boolean
  and (x->>'checked_at')::timestamptz<=now()
  order by (x->>'checked_at')::timestamptz desc,(x->>'price')::numeric,x->>'id' limit 1
 ) recorded on true
 left join lateral (select count(*) n from matched where listing_id=l.x->>'id') counts on true
 left join lateral (
  select x from matched where listing_id=l.x->>'id'
  and live.x is not null and x->>'merchant_slug'<>live.x->>'merchant_slug'
  and (x->>'live_price')::numeric>0 and (x->>'live_checked_at')::timestamptz>now()-interval '6 hours'
  and (x->>'live_checked_at')::timestamptz<=now()
  order by (x->>'live_price')::numeric,x->>'id' limit 1
 ) rival on true
 left join lateral (
  select ph.price,ph.checked_at from public.price_history ph
  where ph.offer_id=(live.x->>'id')::uuid and ph.in_stock and ph.price>0
  and (ph.checked_at at time zone 'Europe/Istanbul')::date<( (live.x->>'live_checked_at')::timestamptz at time zone 'Europe/Istanbul')::date
  and ph.checked_at>=(live.x->>'live_checked_at')::timestamptz-interval '7 days'
  order by ph.checked_at desc,ph.id desc limit 1
 ) old on true
 )
 select x || jsonb_build_object(
 'market_data',true,
 'offer_id',coalesce(live->>'id',x->>'offer_id'),
 'product_url',coalesce(live->>'product_url',x->>'product_url'),
 'affiliate_url',case when live is not null then live->>'affiliate_url' else x->>'affiliate_url' end,
 'merchant_slug',coalesce(live->>'merchant_slug',x->>'merchant_slug'),
 'merchant_name',coalesce(live->>'merchant_name',x->>'merchant_name'),
 'price',case when live is not null then (live->>'live_price')::numeric when x->>'manual_id' is not null then (x->>'price')::numeric end,
 'price_checked_at',case when live is not null then live->>'live_checked_at' when x->>'manual_id' is not null then x->>'price_checked_at' end,
 'competitor_offer_id',rival->>'id','competitor_price',(rival->>'live_price')::numeric,
 'competitor_name',rival->>'merchant_name','competitor_checked_at',rival->>'live_checked_at',
 'old_price',old_price,'old_checked_at',old_checked_at,
 'offer_count',offer_count,'recorded_price',(recorded->>'price')::numeric,'recorded_checked_at',recorded->>'checked_at',
 'recorded_merchant',recorded->>'merchant_name','recorded_offer_id',recorded->>'id',
 'status',case when live is not null then 'verified' else x->>'status' end,
 'checked_at',case when rival is not null then least((live->>'live_checked_at')::timestamptz,(rival->>'live_checked_at')::timestamptz) else (x->>'checked_at')::timestamptz end)
 from enriched order by (x->>'detected_at')::timestamptz desc nulls last,x->>'id'
$$;
revoke all on function public.website_market_catalogue(text) from public,anon,authenticated;
grant execute on function public.website_market_catalogue(text) to service_role;
