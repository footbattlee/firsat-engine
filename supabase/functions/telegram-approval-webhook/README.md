# Telegram approval webhook

Production callback handling is deployed to Supabase Edge Functions as `telegram-approval-webhook`.

Flow: Telegram inline callback -> Edge Function -> Reels selection / rejection / helper actions. Normal Instagram posts are handled by the cloud publication queue.

The normal PAYLAS action on old cards acknowledges the automatic queue; it does not publish immediately. Reels remain a separate manual action. Existing `deal_publications` rows provide per-platform idempotency. See the root PUBLICATION_QUEUE.md for the active schedule.

Required Edge Function secrets (never commit values):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_PUBLISH_CHAT_ID
- TELEGRAM_APPROVAL_CHAT_ID
- TELEGRAM_WEBHOOK_SECRET
- INSTAGRAM_ACCESS_TOKEN
- INSTAGRAM_USER_ID
- FACEBOOK_SYSTEM_USER_TOKEN
- FACEBOOK_PAGE_ID

Optional:
- TELEGRAM_STORY_CHAT_ID (varsayılan: TELEGRAM_APPROVAL_CHAT_ID)
- INSTAGRAM_GRAPH_BASE
- FACEBOOK_GRAPH_VERSION
- INSTAGRAM_MEDIA_BUCKET

Supabase supplies SUPABASE_URL and server-side API credentials to Edge Functions.
