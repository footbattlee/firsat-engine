alter table public.deal_candidates
  add column if not exists notification_reason text,
  add column if not exists redispatch_drop_percent numeric(7,2) not null default 0,
  add column if not exists previous_notified_price numeric(12,2);

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'deal_candidates_notification_reason_check'
      and conrelid = 'public.deal_candidates'::regclass
  ) then
    alter table public.deal_candidates
      add constraint deal_candidates_notification_reason_check
      check (notification_reason is null or notification_reason in ('competitor_gap', 'redispatch_price_drop'));
  end if;
end $$;

update public.deal_candidates
set notification_reason = case
      when gap_percent >= coalesce(threshold_percent, 15) then 'competitor_gap'
      else null
    end,
    redispatch_drop_percent = 0,
    previous_notified_price = null
where notification_reason is null;
