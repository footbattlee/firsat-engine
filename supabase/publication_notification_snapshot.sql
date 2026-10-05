alter table public.deal_approval_dispatches add column if not exists notified_price numeric;
alter table public.publication_queue add column if not exists notification_context jsonb;
