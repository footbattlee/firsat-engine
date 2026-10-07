# Link report correction — 8 October 2026

The previous report described non-bot-looking redirect requests as “unique real clicks”. This was not a valid claim about people. Browser-looking automated requests passed the User-Agent filter, and visitor deduplication was per product/channel/day, not across the whole audience.

## Evidence from production

| Istanbul date | Facebook non-bot requests | Within 3 minutes of a matching publication | Previous reported Facebook total |
|---|---:|---:|---:|
| 6 October | 321 | 134 | 245 |
| 7 October | 154 | 132 | 69 |

Publication proximity is evidence of suspected automated checks, not proof that every nearby visit was a bot. Historical request headers were not stored, so the number of real people cannot be reconstructed.

For Amazon destinations, every inspected link on 6–7 October carried the expected public affiliate tag `anlikindirimr-21`. The old local report counted 80 Amazon link requests on 6 October and 32 on 7 October after its existing filtering/deduplication. These were local tracking measurements, not values imported from Amazon Associates. The attached Amazon screenshot reports 34 clicks on 7 October. Amazon describes its clicks as visits through product links in the selected period: [Amazon report definitions](https://affiliate-program.amazon.com/help/node/topic/GPTZ495QPL6TEZLJ).

Scheduled dispatches at 00:01 Istanbul report the preceding completed calendar day:
- Dispatch 7 October 00:01 → 6 October 00:00 through 7 October 00:00 (end exclusive).
- Dispatch 8 October 00:01 → 7 October 00:00 through 8 October 00:00 (end exclusive).

## Implemented behavior

- Capture Fetch Metadata and preview-purpose headers. Require navigate/document/user-activation metadata before including a request in browser-navigation totals.
- This is a browser signal, not proof of a human; headers can be imitated and some legitimate clients omit them.
- Keep other requests in a separate unverified category. Existing records remain intact and are unverified because the browser headers were not recorded.
- Exclude recognized crawlers and prefetch/prerender traffic; these receive HTTP 200 without a merchant/affiliate redirect.
- Deduplicate daily per product/channel/visitor. A later navigation signal replaces an earlier unverified event in that group. Confirmed browser navigation is not removed merely because it occurs right after publication.
- Both scheduled and manual Telegram reports show exact Istanbul periods, uncertain requests, and explain that Amazon totals are local measurements.
- Preserve normal redirects for clients that omit browser metadata; HEAD creates no click.
- Retain the existing 15-second publication filter only for unverified requests.
- Service-role-only report RPCs, with an empty SECURITY DEFINER search_path.

## Validation

166 Python tests and 315 subtests passed. 42 Node tests passed, including isolated PostgreSQL execution of the migration, exact Istanbul date boundaries, bot/prefetch exclusion, repeat deduplication, early legitimate navigation, report formatting, and anonymous/authenticated RPC permission denial.

The deployed versions are deal-click v4, click-report v4, and telegram-approval-webhook v28. Live probes confirmed crawler GET and prefetch GET return 200 without a merchant redirect, while browser HEAD returns 302 and records no click. Two explicitly bot-classified diagnostic requests were recorded under “other”; they are excluded from opening totals.

Supabase security advisors reported existing RLS-disabled tables canonical_products, product_matches, and deal_candidates; this migration does not change them. Remediation reference: [Supabase RLS linter](https://supabase.com/docs/guides/database/database-linter?lint=0013_rls_disabled_in_public). No new report-function advisory was returned.
