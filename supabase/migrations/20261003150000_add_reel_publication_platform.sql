alter table public.deal_publications
  drop constraint if exists deal_publications_platform_check;

alter table public.deal_publications
  add constraint deal_publications_platform_check
  check (platform = any (array[
    'telegram'::text,
    'instagram'::text,
    'facebook'::text,
    'x'::text,
    'whatsapp'::text,
    'story'::text,
    'reel'::text
  ]));
