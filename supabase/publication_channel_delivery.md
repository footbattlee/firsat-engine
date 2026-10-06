# Automatic publication repair — 6 October 2026

The cloud queue previously published only Instagram and story assets. A timeout after Instagram publication left the database in publishing/held state, suppressing the story message even when the image was live. Story sends interrupted while publishing also had no recovery path.

The worker now reconciles Instagram against the exact candidate tracking parameter and publication window. It persists the container and reserves media_publish once. Successfully published Instagram snapshots create independent Telegram, Facebook and story delivery rows. Each row has a claim token, attempts and retry time; completing a claim cannot overwrite a different claim. Definite API rejections can retry with backoff. Ambiguous external outcomes remain held for review.

Normal Instagram publication keeps the 10:00–23:30 Istanbul half-hour schedule. Channel delivery runs in a separate authenticated invocation, with independent parallel sends, so an Instagram request cannot consume the delivery invocation's execution budget. The five-minute recovery job repairs missing deliveries; public Telegram/Facebook delivery remains within 10:00–23:59. Story files can be recovered outside that window. Telegram images are uploaded as owned PNG files instead of asking Telegram to retrieve a remote URL. Story delivery uses TELEGRAM_STORY_CHAT_ID, configured as Fiyatzade story in the cloud.

## Deployment

Apply publication_channel_delivery.sql after the existing cloud queue, scan scope, notification snapshot and admin scope SQL. Deploy all TypeScript files in functions/publication-queue. The function preserves custom service/queue-token authentication and verify_jwt=false. Apply schedule_publication_queue.sql to install the half-hour publication job and independent recovery job.

Authenticated diagnostics: mode=configuration-test performs target checks without posting; dry_run validates selected creatives without publication. mode=recover repairs proven publications without reserving a new Instagram slot. mode=deliver requires candidate_id and delivers only channels allowed by the service-only claim RPC. No storefront price/stock check runs at publication; the completed scan snapshot and 15% repeat-price threshold remain authoritative.

## Scan duration

The 5 October full scan took 12,964 seconds (3h 36m 04s). Campaign/rival discovery consumed 3,163.5 seconds, ordinary collection approximately 2h 20m, rival refresh 586.3 seconds, matching 47.4 seconds, deal calculation 103.3 seconds and admin dispatch 673.2 seconds. Ordinary collection covered 863 jobs. n11 accounted for 9,529.3 task-seconds across 171 jobs, averaging 55.7 seconds; these task-seconds overlap other stores.

Campaigns now save run-scoped seeds first. After ordinary category collection, one combined rival batch reuses only fresh, in-stock, approved, variant-compatible competitors; it searches missing rivals with at most three merchant streams and deduplicates identical queries. Standalone --find-competitors keeps its immediate behavior. Known-rival refresh also has at most three streams, serial within each merchant.

Collectors reuse one database HTTPS connection per process without retrying writes or routing credentials through a store proxy. n11 reads existing offers/variants/product images in batches and updates images only when needed. Prices, scan timestamps and price history are still persisted for every collected product. Reels retain narration and their vertical H.264 format; the encoder preset defaults to veryfast.

Read-only measurement on 20 actual n11 products: 40 individual reads took 5.327s; three batch reads took 0.651s, and 40 unchanged image writes were unnecessary. Same-story Reels benchmark without narration: medium 3.67s, veryfast 2.84s; both 290 frames and 9.66s. These are component measurements, not a new full-scan timing. Each subsequent pipeline writes reports/pipeline_timings.json with step timings.
