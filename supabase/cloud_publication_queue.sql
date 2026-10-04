create table if not exists public.publication_queue (
  candidate_id uuid primary key references public.deal_candidates(id) on delete cascade,
  canonical_product_id uuid not null unique references public.canonical_products(id),
  state text not null default 'queued' check (state in ('queued','checking','publishing','published','held')),
  enqueued_at timestamptz not null default now(), next_check_at timestamptz not null default now(),
  claim_token uuid, snapshot jsonb, last_error text, updated_at timestamptz not null default now()
);
create index if not exists publication_queue_waiting on public.publication_queue(next_check_at,enqueued_at) where state='queued';
create table if not exists public.publication_slots (
  slot_at timestamptz primary key, candidate_id uuid references public.deal_candidates(id),
  created_at timestamptz not null default now()
);
create table if not exists public.publication_queue_settings (
  id boolean primary key default true check(id), enabled boolean not null default false
);
insert into public.publication_queue_settings(id,enabled) values(true,false) on conflict do nothing;
alter table public.publication_queue enable row level security;
alter table public.publication_slots enable row level security;
alter table public.publication_queue_settings enable row level security;
revoke all on public.publication_queue,public.publication_slots,public.publication_queue_settings from anon,authenticated;
grant all on public.publication_queue,public.publication_slots,public.publication_queue_settings to service_role;

create or replace function public.queue_deal_candidate() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 if new.status='candidate' and not exists(select 1 from public.deal_publications p where p.deal_candidate_id=new.id and p.platform='instagram' and p.status='published') then
  insert into public.publication_queue(candidate_id,canonical_product_id,enqueued_at)
  values(new.id,new.canonical_product_id,coalesce(new.detected_at,now())) on conflict do nothing;
 end if;
 return new;
end; $$;
drop trigger if exists enqueue_publication_candidate on public.deal_candidates;
create trigger enqueue_publication_candidate after insert or update on public.deal_candidates for each row execute function public.queue_deal_candidate();

create or replace function public.check_publication_queue_token(p_token text) returns boolean
language sql security definer set search_path='' as $$
 select length(p_token)=64 and exists(select 1 from vault.decrypted_secrets where name='publication_queue_token' and decrypted_secret=p_token);
$$;

create or replace function public.start_publication_slot() returns timestamptz
language plpgsql security definer set search_path='' as $$
declare t timestamp:=now() at time zone 'Europe/Istanbul'; s timestamptz; inserted timestamptz;
begin
 if not coalesce((select enabled from public.publication_queue_settings where id),false) or extract(hour from t)<10 or extract(hour from t)>23 or (extract(minute from t)::int % 30)>=5 then return null; end if;
 s:=(date_trunc('hour',t)+make_interval(mins=>(extract(minute from t)::int/30)*30)) at time zone 'Europe/Istanbul';
 insert into public.publication_slots(slot_at) values(s) on conflict do nothing returning slot_at into inserted;
 return inserted;
end; $$;

create or replace function public.claim_publication_item(p_slot timestamptz) returns setof public.publication_queue
language plpgsql security definer set search_path='' as $$
begin
 if not exists(select 1 from public.publication_slots where slot_at=p_slot and candidate_id is null) or now()>p_slot+interval '5 minutes' then return; end if;
 update public.publication_queue q set state='published',updated_at=now()
 where state in ('queued','checking') and exists(select 1 from public.deal_publications p where p.deal_candidate_id=q.candidate_id and p.platform='instagram' and p.status='published');
 update public.publication_queue set state='queued',claim_token=null where state='checking' and updated_at<now()-interval '10 minutes';
 return query update public.publication_queue set state='checking',claim_token=gen_random_uuid(),updated_at=now()
 where candidate_id=(select q.candidate_id from public.publication_queue q join public.deal_candidates dc on dc.id=q.candidate_id
 where q.state='queued' and q.next_check_at<=now() and dc.status='candidate'
 order by q.next_check_at,q.enqueued_at,q.candidate_id limit 1 for update of q skip locked) returning *;
end; $$;

create or replace function public.begin_publication(p_id uuid,p_claim uuid,p_slot timestamptz,p_snapshot jsonb) returns boolean
language plpgsql security definer set search_path='' as $$
declare reserved uuid;
begin
 if now()>p_slot+interval '5 minutes' or not exists(select 1 from public.publication_queue where candidate_id=p_id and state='checking' and claim_token=p_claim)
 or not exists(select 1 from public.deal_candidates where id=p_id and status='candidate')
 or exists(select 1 from public.deal_publications where deal_candidate_id=p_id and platform='instagram' and status in ('published','publishing','failed')) then return false; end if;
 update public.publication_slots set candidate_id=p_id where slot_at=p_slot and candidate_id is null returning candidate_id into reserved;
 if reserved is null then return false; end if;
 update public.publication_queue set state='publishing',snapshot=p_snapshot,updated_at=now() where candidate_id=p_id and claim_token=p_claim;
 insert into public.deal_publications(deal_candidate_id,platform,status) values(p_id,'instagram','publishing'),(p_id,'story','pending') on conflict(deal_candidate_id,platform) do nothing;
 update public.deal_publications set status='publishing',updated_at=now() where deal_candidate_id=p_id and platform='instagram';
 return true;
end; $$;

revoke all on function public.queue_deal_candidate(),public.check_publication_queue_token(text),public.start_publication_slot(),public.claim_publication_item(timestamptz),public.begin_publication(uuid,uuid,timestamptz,jsonb) from public,anon,authenticated;
grant execute on function public.check_publication_queue_token(text),public.start_publication_slot(),public.claim_publication_item(timestamptz),public.begin_publication(uuid,uuid,timestamptz,jsonb) to service_role;

insert into public.publication_queue(candidate_id,canonical_product_id,enqueued_at)
select dc.id,dc.canonical_product_id,dc.detected_at from public.deal_candidates dc where dc.status='candidate'
and not exists(select 1 from public.deal_publications p where p.deal_candidate_id=dc.id and p.platform='instagram' and p.status='published') on conflict do nothing;

do $$ begin
 if not exists(select 1 from vault.secrets where name='publication_queue_token') then
  perform vault.create_secret(encode(extensions.gen_random_bytes(32),'hex'),'publication_queue_token');
 end if;
end $$;