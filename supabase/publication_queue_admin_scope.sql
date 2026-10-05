
-- Only an admin notification from the originating scan creates queue provenance.
-- Later scans may refresh prices without replacing a waiting item's provenance.
create or replace function public.publication_candidate_is_eligible(p_id uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select exists(
  select 1 from public.publication_queue q
  join public.deal_candidates dc on dc.id=q.candidate_id
  join public.publication_queue_settings s on s.id
  join public.publication_scan_batches origin on origin.started_at=q.source_run_started_at
  join public.publication_scan_batches latest on latest.started_at=dc.scan_started_at
  join public.deal_approval_dispatches a on a.deal_candidate_id=dc.id
  where q.candidate_id=p_id and dc.status='candidate'
    and q.source_run_started_at>=coalesce(s.source_after,'-infinity'::timestamptz)
    and dc.scan_started_at>=q.source_run_started_at
    and origin.completed_at is not null and latest.completed_at is not null
    and (coalesce(q.notification_context->>'notification_reason',dc.notification_reason,'')<>'redispatch_price_drop'
      or (coalesce((q.notification_context->>'previous_notified_price')::numeric,dc.previous_notified_price)>0
        and (1-dc.cheapest_price/coalesce((q.notification_context->>'previous_notified_price')::numeric,dc.previous_notified_price))*100 >= 15))
    and a.status='sent' and a.sent_at>=q.source_run_started_at
    and (q.notification_context is not null or a.created_at>=q.source_run_started_at)
    and not exists(select 1 from public.deal_publications p
      where p.deal_candidate_id=p_id and p.platform='instagram'
      and p.status in ('published','publishing','failed'))
 );
$$;

create or replace function public.enqueue_admin_publication(p_id uuid) returns void
language plpgsql security definer set search_path='' as $$
begin
 insert into public.publication_queue(candidate_id,canonical_product_id,enqueued_at,source_run_started_at,notification_context)
 select dc.id,dc.canonical_product_id,now(),dc.scan_started_at,
 jsonb_build_object('notification_reason',dc.notification_reason,'previous_notified_price',dc.previous_notified_price,'redispatch_drop_percent',dc.redispatch_drop_percent)
 from public.deal_candidates dc
 join public.publication_queue_settings s on s.id
 join public.publication_scan_batches b on b.started_at=dc.scan_started_at
 join public.deal_approval_dispatches a on a.deal_candidate_id=dc.id
 where dc.id=p_id and dc.status='candidate'
   and dc.scan_started_at>=coalesce(s.source_after,'-infinity'::timestamptz)
   and a.status='sent' and a.sent_at>=dc.scan_started_at
   and not exists(select 1 from public.deal_publications p
     where p.deal_candidate_id=dc.id and p.platform='instagram'
     and p.status in ('published','publishing','failed'))
 on conflict(candidate_id) do update
 set source_run_started_at=excluded.source_run_started_at,notification_context=excluded.notification_context,enqueued_at=now(),
     state='queued',next_check_at=now(),claim_token=null,last_error=null,snapshot=null,updated_at=now()
 where publication_queue.state='held'
   and (publication_queue.last_error in ('Excluded: previous scan','Excluded: previous admin notification')
     or (publication_queue.last_error='Excluded: legacy repeat baseline unavailable'
       and excluded.source_run_started_at>publication_queue.source_run_started_at));
end $$;

create or replace function public.queue_deal_candidate() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 perform public.enqueue_admin_publication(new.id);
 return new;
end $$;

create or replace function public.queue_admin_notification() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 if new.status='sent' then perform public.enqueue_admin_publication(new.deal_candidate_id); end if;
 return new;
end $$;
drop trigger if exists enqueue_publication_admin_notification on public.deal_approval_dispatches;
create trigger enqueue_publication_admin_notification
 after insert or update of status,sent_at on public.deal_approval_dispatches
 for each row execute function public.queue_admin_notification();

create or replace function public.start_publication_slot() returns timestamptz
language plpgsql security definer set search_path='' as $$
declare t timestamp:=now() at time zone 'Europe/Istanbul'; s timestamptz; inserted timestamptz; settings public.publication_queue_settings;
begin
 select * into settings from public.publication_queue_settings where id;
 if not coalesce(settings.enabled,false) or now()<coalesce(settings.not_before,'-infinity'::timestamptz)
 or extract(hour from t)<10 or extract(hour from t)>23 or (extract(minute from t)::int%30)>=5
 or not exists(select 1 from public.publication_queue q
   where q.state='queued' and q.next_check_at<=now()
   and public.publication_candidate_is_eligible(q.candidate_id)) then return null;end if;
 s:=(date_trunc('hour',t)+make_interval(mins=>(extract(minute from t)::int/30)*30)) at time zone 'Europe/Istanbul';
 insert into public.publication_slots(slot_at) values(s) on conflict do nothing returning slot_at into inserted;
 return inserted;
end $$;

create or replace function public.claim_publication_item(p_slot timestamptz) returns setof public.publication_queue
language plpgsql security definer set search_path='' as $$
begin
 if not exists(select 1 from public.publication_queue_settings
   where id and enabled and now()>=coalesce(not_before,'-infinity'::timestamptz))
 or p_slot>now() or now()>p_slot+interval '5 minutes'
 or not exists(select 1 from public.publication_slots where slot_at=p_slot and candidate_id is null) then return;end if;
 update public.publication_queue q set state='published',updated_at=now() where state in ('queued','checking')
 and exists(select 1 from public.deal_publications p where p.deal_candidate_id=q.candidate_id and p.platform='instagram' and p.status='published');
 update public.publication_queue set state='queued',claim_token=null
 where state='checking' and updated_at<now()-interval '10 minutes';
 return query update public.publication_queue set state='checking',claim_token=gen_random_uuid(),updated_at=now()
 where candidate_id=(select q.candidate_id from public.publication_queue q
 where q.state='queued' and q.next_check_at<=now()
 and public.publication_candidate_is_eligible(q.candidate_id)
 order by q.next_check_at,q.enqueued_at,q.candidate_id limit 1 for update of q skip locked)
 returning *;
end $$;

create or replace function public.begin_publication(p_id uuid,p_claim uuid,p_slot timestamptz,p_snapshot jsonb) returns boolean
language plpgsql security definer set search_path='' as $$
declare reserved uuid;
begin
 if not exists(select 1 from public.publication_queue_settings
   where id and enabled and now()>=coalesce(not_before,'-infinity'::timestamptz))
 or p_slot>now() or now()>p_slot+interval '5 minutes'
 or not public.publication_candidate_is_eligible(p_id)
 or not exists(select 1 from public.publication_queue
   where candidate_id=p_id and state='checking' and claim_token=p_claim) then return false;end if;
 update public.publication_slots set candidate_id=p_id where slot_at=p_slot and candidate_id is null returning candidate_id into reserved;
 if reserved is null then return false;end if;
 update public.publication_queue set state='publishing',snapshot=p_snapshot,updated_at=now() where candidate_id=p_id and claim_token=p_claim;
 insert into public.deal_publications(deal_candidate_id,platform,status)
 values(p_id,'instagram','publishing'),(p_id,'story','pending') on conflict(deal_candidate_id,platform) do nothing;
 update public.deal_publications set status='publishing',updated_at=now() where deal_candidate_id=p_id and platform='instagram';
 return true;
end $$;

revoke all on function public.publication_candidate_is_eligible(uuid),public.enqueue_admin_publication(uuid),
 public.queue_deal_candidate(),public.queue_admin_notification(),public.start_publication_slot(),
 public.claim_publication_item(timestamptz),public.begin_publication(uuid,uuid,timestamptz,jsonb) from public,anon,authenticated;
grant execute on function public.publication_candidate_is_eligible(uuid),public.start_publication_slot(),
 public.claim_publication_item(timestamptz),public.begin_publication(uuid,uuid,timestamptz,jsonb) to service_role;
