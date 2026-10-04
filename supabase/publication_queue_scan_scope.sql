
alter table public.publication_queue_settings add column if not exists not_before timestamptz;
alter table public.publication_queue_settings add column if not exists source_after timestamptz;
create table if not exists public.publication_scan_batches(started_at timestamptz primary key,completed_at timestamptz);
alter table public.publication_scan_batches enable row level security;
revoke all on public.publication_scan_batches from anon,authenticated;
grant all on public.publication_scan_batches to service_role;
alter table public.deal_candidates add column if not exists scan_started_at timestamptz;
alter table public.publication_queue add column if not exists source_run_started_at timestamptz;
update public.publication_queue_settings set enabled=false,not_before='2026-10-05T07:00:00Z',source_after='2026-10-04T17:53:03Z' where id;
update public.publication_queue set state='held',last_error='Excluded: previous scan',updated_at=now() where state in ('queued','checking') and (source_run_started_at is null or source_run_started_at<'2026-10-04T17:53:03Z');
create or replace function public.queue_deal_candidate() returns trigger language plpgsql security definer set search_path='' as $$
declare cutoff timestamptz;
begin
 select source_after into cutoff from public.publication_queue_settings where id;
 if new.status='candidate' and new.scan_started_at is not null and new.scan_started_at>=coalesce(cutoff,'-infinity'::timestamptz)
 and exists(select 1 from public.publication_scan_batches where started_at=new.scan_started_at)
 and not exists(select 1 from public.deal_publications p where p.deal_candidate_id=new.id and p.platform='instagram' and p.status='published') then
  insert into public.publication_queue(candidate_id,canonical_product_id,enqueued_at,source_run_started_at)
  values(new.id,new.canonical_product_id,now(),new.scan_started_at)
  on conflict(candidate_id) do update set source_run_started_at=excluded.source_run_started_at,state='queued',next_check_at=now(),claim_token=null,last_error=null,snapshot=null,updated_at=now()
  where publication_queue.state='queued' or (publication_queue.state='held' and publication_queue.last_error='Excluded: previous scan');
 end if;return new;
end $$;
create or replace function public.complete_publication_scan(p_started_at timestamptz) returns void language sql security definer set search_path='' as $$
 update public.publication_scan_batches set completed_at=now() where started_at=p_started_at;
$$;
revoke all on function public.complete_publication_scan(timestamptz) from public,anon,authenticated;
grant execute on function public.complete_publication_scan(timestamptz) to service_role;
create or replace function public.start_publication_slot() returns timestamptz language plpgsql security definer set search_path='' as $$
declare t timestamp:=now() at time zone 'Europe/Istanbul'; s timestamptz; inserted timestamptz; settings public.publication_queue_settings;
begin
 select * into settings from public.publication_queue_settings where id;
 if not settings.enabled or now()<coalesce(settings.not_before,'-infinity'::timestamptz)
 or extract(hour from t)<10 or extract(hour from t)>23 or (extract(minute from t)::int%30)>=5
 or not exists(select 1 from public.publication_queue q join public.publication_scan_batches b on b.started_at=q.source_run_started_at
 where q.state='queued' and b.completed_at is not null and q.source_run_started_at>=coalesce(settings.source_after,'-infinity'::timestamptz)) then return null;end if;
 s:=(date_trunc('hour',t)+make_interval(mins=>(extract(minute from t)::int/30)*30)) at time zone 'Europe/Istanbul';
 insert into public.publication_slots(slot_at) values(s) on conflict do nothing returning slot_at into inserted;return inserted;
end $$;
create or replace function public.claim_publication_item(p_slot timestamptz) returns setof public.publication_queue language plpgsql security definer set search_path='' as $$
begin
 if not exists(select 1 from public.publication_slots where slot_at=p_slot and candidate_id is null) or now()>p_slot+interval '5 minutes' then return;end if;
 update public.publication_queue q set state='published',updated_at=now() where state in ('queued','checking')
 and exists(select 1 from public.deal_publications p where p.deal_candidate_id=q.candidate_id and p.platform='instagram' and p.status='published');
 update public.publication_queue set state='queued',claim_token=null where state='checking' and updated_at<now()-interval '10 minutes';
 return query update public.publication_queue set state='checking',claim_token=gen_random_uuid(),updated_at=now()
 where candidate_id=(select q.candidate_id from public.publication_queue q join public.deal_candidates dc on dc.id=q.candidate_id
 join public.publication_scan_batches b on b.started_at=q.source_run_started_at
 join public.publication_queue_settings s on s.id
 where q.state='queued' and q.next_check_at<=now() and dc.status='candidate' and b.completed_at is not null
 and dc.scan_started_at=q.source_run_started_at and q.source_run_started_at>=coalesce(s.source_after,'-infinity'::timestamptz)
 order by q.next_check_at,q.enqueued_at,q.candidate_id limit 1 for update of q skip locked) returning *;
end $$;

create or replace function public.begin_publication(p_id uuid,p_claim uuid,p_slot timestamptz,p_snapshot jsonb) returns boolean
language plpgsql security definer set search_path='' as $$
declare reserved uuid;
begin
 if not exists(select 1 from public.publication_queue_settings where id and enabled and now()>=coalesce(not_before,'-infinity'::timestamptz))
 or now()>p_slot+interval '5 minutes'
 or not exists(select 1 from public.publication_queue q join public.publication_scan_batches b on b.started_at=q.source_run_started_at
 join public.publication_queue_settings s on s.id join public.deal_candidates dc on dc.id=q.candidate_id
 where q.candidate_id=p_id and q.state='checking' and q.claim_token=p_claim and b.completed_at is not null and dc.status='candidate'
 and dc.scan_started_at=q.source_run_started_at and q.source_run_started_at>=coalesce(s.source_after,'-infinity'::timestamptz))
 or exists(select 1 from public.deal_publications where deal_candidate_id=p_id and platform='instagram' and status in ('published','publishing','failed')) then return false;end if;
 update public.publication_slots set candidate_id=p_id where slot_at=p_slot and candidate_id is null returning candidate_id into reserved;
 if reserved is null then return false;end if;
 update public.publication_queue set state='publishing',snapshot=p_snapshot,updated_at=now() where candidate_id=p_id and claim_token=p_claim;
 insert into public.deal_publications(deal_candidate_id,platform,status) values(p_id,'instagram','publishing'),(p_id,'story','pending') on conflict(deal_candidate_id,platform) do nothing;
 update public.deal_publications set status='publishing',updated_at=now() where deal_candidate_id=p_id and platform='instagram';
 return true;
end $$;

update public.publication_queue_settings set enabled=true where id;
