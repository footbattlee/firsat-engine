-- Apply only after approval. Preserve published and ambiguous Instagram outcomes.
update public.publication_queue q
set state='held',claim_token=null,last_error='Excluded: previous admin notification',updated_at=now()
where q.state in ('queued','checking')
  and q.source_run_started_at >= (select source_after from public.publication_queue_settings where id)
  and not exists(select 1 from public.deal_approval_dispatches a
    where a.deal_candidate_id=q.candidate_id and a.status='sent'
    and a.sent_at>=q.source_run_started_at);
