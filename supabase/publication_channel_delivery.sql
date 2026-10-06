alter table public.deal_publications
 add column if not exists delivery_claim uuid,
 add column if not exists delivery_attempts integer not null default 0,
 add column if not exists next_attempt_at timestamptz not null default now(),
 add column if not exists container_id text,
 add column if not exists publish_requested_at timestamptz;
create index if not exists publication_delivery_waiting
 on public.deal_publications(next_attempt_at) where status in ('pending','failed');

create or replace function public.ensure_publication_channels(p_id uuid) returns void
language sql security definer set search_path='' as $$
 insert into public.deal_publications(deal_candidate_id,platform,status)
 select q.candidate_id,c.platform,'pending' from public.publication_queue q
 join public.publication_queue_settings s on s.id and s.enabled
 cross join (values('telegram'),('facebook'),('story')) c(platform)
 where q.candidate_id=p_id and q.state='published' and q.snapshot is not null
 and not exists(select 1 from public.deal_candidates dc where dc.id=q.candidate_id and dc.status='rejected')
 and q.source_run_started_at>=coalesce(s.source_after,'-infinity'::timestamptz)
 and exists(select 1 from public.deal_publications p where p.deal_candidate_id=q.candidate_id and p.platform='instagram' and p.status='published')
 on conflict(deal_candidate_id,platform) do nothing;
$$;
create or replace function public.claim_publication_channel(p_id uuid,p_platform text) returns uuid
language plpgsql security definer set search_path='' as $$
declare token uuid;
begin
 if p_platform not in ('story','telegram','facebook') then return null;end if;
 if p_platform<>'story' and extract(hour from now() at time zone 'Europe/Istanbul') not between 10 and 23 then return null;end if;
 if exists(select 1 from public.deal_candidates where id=p_id and status='rejected') then return null;end if;
 perform public.ensure_publication_channels(p_id);
 -- Interrupted network sends are ambiguous; never blindly duplicate them.
 update public.deal_publications set status='failed',error_message='interrupted-delivery-outcome-unknown',
 next_attempt_at='infinity',delivery_claim=null,updated_at=now()
 where deal_candidate_id=p_id and platform=p_platform and status='publishing' and updated_at<now()-interval '10 minutes';
 update public.deal_publications p set status='publishing',delivery_claim=gen_random_uuid(),
 delivery_attempts=delivery_attempts+1,updated_at=now()
 where p.deal_candidate_id=p_id and p.platform=p_platform
 and p.status in ('pending','failed') and p.next_attempt_at<=now()
 and exists(select 1 from public.publication_queue q join public.publication_queue_settings s on s.id and s.enabled
 where q.candidate_id=p_id and q.state='published' and q.snapshot is not null
 and q.source_run_started_at>=coalesce(s.source_after,'-infinity'::timestamptz))
 and exists(select 1 from public.deal_publications i where i.deal_candidate_id=p_id and i.platform='instagram' and i.status='published')
 returning p.delivery_claim into token;
 return token;
end $$;
create or replace function public.finish_publication_channel(p_id uuid,p_platform text,p_claim uuid,p_result jsonb) returns boolean
language plpgsql security definer set search_path='' as $$
declare affected integer;
begin
 if p_platform not in ('story','telegram','facebook') or p_result->>'status' not in ('published','failed') then return false;end if;
 update public.deal_publications set status=p_result->>'status',
 external_post_id=case when p_result->>'status'='published' then p_result->>'external_post_id' else external_post_id end,
 published_at=case when p_result->>'status'='published' then (p_result->>'published_at')::timestamptz else published_at end,
 error_message=left(p_result->>'error_message',200),
 next_attempt_at=coalesce((p_result->>'next_attempt_at')::timestamptz,'infinity'::timestamptz),
 delivery_claim=null,updated_at=now()
 where deal_candidate_id=p_id and platform=p_platform and status='publishing' and delivery_claim=p_claim;
 get diagnostics affected=row_count;
 return affected=1;
end $$;
revoke all on function public.ensure_publication_channels(uuid),public.claim_publication_channel(uuid,text),
 public.finish_publication_channel(uuid,text,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.ensure_publication_channels(uuid),public.claim_publication_channel(uuid,text),
 public.finish_publication_channel(uuid,text,uuid,jsonb) to service_role;

create or replace function public.pending_publication_deliveries(p_limit integer default 3) returns setof public.publication_queue
language plpgsql security definer set search_path='' as $$
begin
 insert into public.deal_publications(deal_candidate_id,platform,status)
 select q.candidate_id,c.platform,'pending' from public.publication_queue q
 join public.publication_queue_settings s on s.id and s.enabled
 cross join (values('telegram'),('facebook'),('story')) c(platform)
 where q.state='published' and q.snapshot is not null
 and not exists(select 1 from public.deal_candidates dc where dc.id=q.candidate_id and dc.status='rejected')
 and q.source_run_started_at>=coalesce(s.source_after,'-infinity'::timestamptz)
 and exists(select 1 from public.deal_publications i where i.deal_candidate_id=q.candidate_id and i.platform='instagram' and i.status='published')
 on conflict(deal_candidate_id,platform) do nothing;
 return query select q.* from public.publication_queue q
 join public.publication_queue_settings s on s.id and s.enabled
 where q.state='published' and q.snapshot is not null
 and q.source_run_started_at>=coalesce(s.source_after,'-infinity'::timestamptz)
 and exists(select 1 from public.deal_publications p where p.deal_candidate_id=q.candidate_id and p.platform in ('story','telegram','facebook')
 and (p.platform='story' or extract(hour from now() at time zone 'Europe/Istanbul') between 10 and 23)
 and ((p.status in ('pending','failed') and p.next_attempt_at<=now()) or (p.status='publishing' and p.updated_at<now()-interval '10 minutes')))
 order by exists(select 1 from public.deal_publications p where p.deal_candidate_id=q.candidate_id and p.platform='story' and p.status in ('pending','failed') and p.next_attempt_at<=now()) desc,q.enqueued_at limit greatest(1,least(p_limit,10));
end $$;
revoke all on function public.pending_publication_deliveries(integer) from public,anon,authenticated;
grant execute on function public.pending_publication_deliveries(integer) to service_role;
