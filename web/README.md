# Fırsatcı homepage

Run `pnpm install --ignore-scripts`, then `pnpm build` or `pnpm dev`.
Server-only environment: `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Never use a NEXT_PUBLIC service key.

## Price and link rules
- The homepage reads private `homepage_deals` snapshots rather than historical deal candidate prices.
- Verified prices expire after 60 minutes; manual entries also expire at their specified time.
- Automatic price comparisons require two currently verified stores, approved product matches, and a 15%–69.99% advantage.
- Competitor prices are labelled as competitor prices, never as the product's previous price.
- Store access failures show product discovery cards with no price or discount promise. Identity failures, removed listings, HTTP 404, and expired entries are hidden. Discovery entries expire after 24 hours without a refresh attempt.
- Price-based buttons use `/go/[id]`, which checks freshness before redirecting.
- Discovery buttons use `/urun/[id]`; these promise only a store product link.
- Both routes preserve the original affiliate URL and query parameters, restrict merchant hosts and reject unsafe destinations.
- Stored non-Amazon links currently have no affiliate attribution. Manual Hepsiburada affiliate links are supported; they must be supplied by the owner.

## Refresh
Deploy `supabase/functions/homepage-refresh`, apply `homepage_deals.sql`, and then `homepage_schedule.sql`.
The private worker checks nine listings per call, three in parallel; a five-minute database schedule rotates through up to 60 candidates and 30 manual entries. The browser refreshes its listing once per minute while visible.
Authentication uses the existing private publication token from Vault. Public/anonymous calls cannot refresh prices or write data.

**Current limitation:** direct cloud requests may return no Amazon buy box, or store HTTP 403/404. The worker deliberately fails closed. This does not mean the store is necessarily out of stock. A browser or an authorized store feed is needed before claiming continuous verified-price coverage; no paid proxy is enabled.

## Manual Hepsiburada entries
Insert through the server/admin connection into `homepage_manual_deals`: title, optional brand/image_url, merchant_slug='hepsiburada', the normal product_url, the owner's full affiliate_url, and an explicit expires_at. Do not insert a guessed price. The worker checks the normal product page, and outbound clicks use the full affiliate_url. No public write or admin UI is exposed.

## Checks
From the repository root:
`node --experimental-strip-types --test tests/test_homepage.mjs`

The suite covers freshness, affiliate preservation, host restrictions, manual links, Turkish price parsing, mismatched visible/schema prices, membership-only prices, stock evidence and discovery fallback.
