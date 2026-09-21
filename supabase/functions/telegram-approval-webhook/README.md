# Telegram approval webhook

Production callback handling is deployed to Supabase Edge Functions as `telegram-approval-webhook`.

Flow: Telegram inline callback -> Edge Function -> Supabase publication state -> Telegram public channel + Instagram + Facebook.

The cloud handler reuses the photo attached to the admin approval message, so PAYLAŞ/REDDET does not depend on a local PC or Pillow process. Existing `deal_publications` rows provide per-platform idempotency.

Required Edge Function secrets (never commit values):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_PUBLISH_CHAT_ID
- TELEGRAM_WEBHOOK_SECRET
- INSTAGRAM_ACCESS_TOKEN
- INSTAGRAM_USER_ID
- FACEBOOK_SYSTEM_USER_TOKEN
- FACEBOOK_PAGE_ID

Optional:
- INSTAGRAM_GRAPH_BASE
- FACEBOOK_GRAPH_VERSION
- INSTAGRAM_MEDIA_BUCKET

Supabase supplies SUPABASE_URL and server-side API credentials to Edge Functions.
