update public.deal_candidates
set status = 'expired',
    verified = false,
    verified_at = null,
    updated_at = now()
where status = 'candidate'
  and gap_percent < coalesce(threshold_percent, 15)
  and notification_reason is null;
