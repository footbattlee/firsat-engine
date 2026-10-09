
-- Server-only catalogue. No synthetic prices or history rows are created.
create or replace function public.website_catalogue(p_listing_id text default null)
returns setof jsonb language sql stable security invoker set search_path='' set statement_timeout='5s' as $$
 with automatic as (
 select d.id::text id,d.id candidate_id,d.canonical_product_id,d.detected_at,d.competitor_offer_id,
 o.id offer_id,o.product_url,o.affiliate_url,o.image_url,o.merchant_id,
 cp.title,cp.brand,cat.slug category_slug,cat.name category_name
 from public.deal_candidates d
 join public.canonical_products cp on cp.id=d.canonical_product_id and cp.active
 join public.offers o on o.id=d.cheapest_offer_id
 join public.product_variants v on v.id=o.product_variant_id and v.active
 join public.products p on p.id=v.product_id and p.active
 join public.merchants m on m.id=o.merchant_id and m.active
 join public.offers ro on ro.id=d.competitor_offer_id
 join public.product_variants rv on rv.id=ro.product_variant_id and rv.active
 left join public.categories cat on cat.id=p.category_id
 where d.status='candidate' and (p_listing_id is null or d.id::text=p_listing_id)
 and exists(select 1 from public.product_matches pm where pm.canonical_product_id=d.canonical_product_id and pm.product_id=v.product_id and pm.status='approved')
 and exists(select 1 from public.product_matches pm where pm.canonical_product_id=d.canonical_product_id and pm.product_id=rv.product_id and pm.status='approved')
 and (v.gtin is null or rv.gtin is null or v.gtin=rv.gtin)
 ), listings as (
 select a.id,a.candidate_id,null::uuid manual_id,a.canonical_product_id,a.detected_at,a.offer_id,a.competitor_offer_id,
 a.title,a.brand,a.product_url,a.affiliate_url,a.image_url,m.slug merchant_slug,m.name merchant_name,
 null::timestamptz expires_at,a.category_slug,a.category_name
 from automatic a join public.merchants m on m.id=a.merchant_id
 union all
 select 'manual-'||d.id,null::uuid,d.id,null::uuid,null::timestamptz,null::uuid,null::uuid,
 d.title,d.brand,d.product_url,d.affiliate_url,d.image_url,m.slug,m.name,d.expires_at,null::text,null::text
 from public.homepage_manual_deals d join public.merchants m on m.slug=d.merchant_slug and m.active
 where d.active and d.expires_at>now() and (p_listing_id is null or 'manual-'||d.id=p_listing_id)
 )
 select jsonb_build_object('id',l.id,'candidate_id',l.candidate_id,'manual_id',l.manual_id,
 'canonical_product_id',l.canonical_product_id,'offer_id',l.offer_id,'competitor_offer_id',l.competitor_offer_id,'detected_at',l.detected_at,
 'title',coalesce(nullif(h.title,''),l.title),'brand',l.brand,
 'product_url',l.product_url,'affiliate_url',l.affiliate_url,'image_url',coalesce(h.image_url,l.image_url),
 'merchant_slug',l.merchant_slug,'merchant_name',l.merchant_name,'expires_at',l.expires_at,
 'category_slug',l.category_slug,'category_name',l.category_name,'catalogue_active',true,
 'status',coalesce(h.status,'pending'),'price',h.price,'competitor_price',h.competitor_price,
 'competitor_name',h.competitor_name,'checked_at',h.checked_at,'price_checked_at',h.price_checked_at,
 'attempted_at',h.attempted_at,'error_code',h.error_code)
 from listings l left join public.homepage_deals h on h.id=l.id and h.status<>'ended'
 and (h.offer_id=l.offer_id or l.manual_id is not null)
 order by l.detected_at desc nulls last,l.id
$$;
revoke all on function public.website_catalogue(text) from public,anon,authenticated;
grant execute on function public.website_catalogue(text) to service_role;

create or replace function public.website_product_offers(p_listing_id text)
returns setof jsonb language sql stable security invoker set search_path='' set statement_timeout='5s' as $$
 with anchor as (
 select (x->>'canonical_product_id')::uuid canonical_id,(x->>'offer_id')::uuid offer_id
 from public.website_catalogue(p_listing_id) x where x->>'manual_id' is null
 )
 select jsonb_build_object('id',o.id,'merchant_name',m.name,'merchant_slug',m.slug,'seller',o.seller_name,
 'price',o.price,'in_stock',o.in_stock,'checked_at',o.last_checked_at,
 'product_url',o.product_url,'affiliate_url',o.affiliate_url)
 from anchor a join public.offers ao on ao.id=a.offer_id
 join public.product_variants av on av.id=ao.product_variant_id
 join public.product_matches pm on pm.canonical_product_id=a.canonical_id and pm.status='approved'
 join public.products p on p.id=pm.product_id and p.active
 join public.product_variants v on v.product_id=p.id and v.active
 join public.offers o on o.product_variant_id=v.id
 join public.merchants m on m.id=o.merchant_id and m.active
 where o.currency='TRY'
 and (o.id=a.offer_id or (
   (av.gtin is null or v.gtin=av.gtin)
   and lower(coalesce(v.color,''))=lower(coalesce(av.color,''))
   and lower(coalesce(v.size,''))=lower(coalesce(av.size,''))
   and lower(coalesce(v.capacity,''))=lower(coalesce(av.capacity,''))))
 order by o.in_stock desc nulls last,o.price asc nulls last,o.id
$$;
revoke all on function public.website_product_offers(text) from public,anon,authenticated;
grant execute on function public.website_product_offers(text) to service_role;

create or replace function public.website_price_history(p_listing_id text)
returns setof jsonb language sql stable security invoker set search_path='' set statement_timeout='5s' as $$
 with matched as (select x from public.website_product_offers(p_listing_id) x),
 daily as (
 select ph.offer_id,ph.price,ph.checked_at,(ph.checked_at at time zone 'Europe/Istanbul')::date as price_day,
 m.x->>'merchant_name' merchant_name,
 row_number() over(partition by ph.offer_id,(ph.checked_at at time zone 'Europe/Istanbul')::date order by ph.checked_at desc,ph.id desc) rn
 from matched m join public.price_history ph on ph.offer_id=(m.x->>'id')::uuid
 where ph.checked_at>=now()-interval '90 days' and ph.checked_at<=now()
 and ph.price>0 and ph.in_stock=true
 )
 select jsonb_build_object('offer_id',offer_id,'merchant',merchant_name,'day',price_day,'price',price,'checked_at',checked_at)
 from daily where rn=1 order by price_day,merchant_name,offer_id
$$;
revoke all on function public.website_price_history(text) from public,anon,authenticated;
grant execute on function public.website_price_history(text) to service_role;
