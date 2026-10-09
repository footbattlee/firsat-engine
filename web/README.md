# Fırsatcı homepage

Run `pnpm install --ignore-scripts`, then `pnpm build` or `pnpm dev`.
Server-only environment: `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Never use a NEXT_PUBLIC service key.

## Price and link rules
- The homepage reads all active approved listings through the private website_market_catalogue RPC. No 60-product cap; the UI paginates 24 cards.
- The default opportunity feed only shows verified purchase prices with a 15%–69.99% daily drop or verified competitor advantage, plus verified manual entries. The checked-price tab and full catalogue remain accessible.
- Purchase checks expire after 6 hours. Historical scan prices up to 7 days old only appear as dated records in the full catalogue; they never imply a current buy price.
- Daily price drops compare the same offer against its latest in-stock pipeline record from an earlier Istanbul calendar day, within 7 days. Competitor comparisons require two independently verified offers at different merchants; the two bases have separate labels.
- website_offer_checks retains independent purchase checks even when a rival check fails. Temporary access errors retain the original successful check timestamp; stock/identity/price verification failures disable that check. Offer URL changes and newer out-of-stock daily records invalidate it.
- Broader comparisons only include approved same-variant matches. Shipping is explicitly unverified; coupon, minimum-quantity and member-only prices are not treated as standard purchase prices.
- Product details use /urun-detay/[id]; product links use /urun/[id] and exact matched store offers use /magaza/[id]?offer=... . The legacy /go/[id] route retains its older stricter snapshot freshness rule.
- Outbound routes preserve the full original affiliate URL and query parameters, restrict merchant hosts and reject unsafe destinations.
- Stored non-Amazon links currently have no affiliate attribution. Manual Hepsiburada affiliate links are supported; they must be supplied by the owner.

## Refresh
Deploy `supabase/functions/homepage-refresh`, apply `homepage_deals.sql`, apply website_catalogue.sql and website_market.sql, and then `homepage_schedule.sql`.
The private worker checks nine listings per call, three in parallel; a five-minute database schedule rotates through all active candidates and manual entries. The browser refreshes its listing once per minute while visible.
Authentication uses the existing private publication token from Vault. Public/anonymous calls cannot refresh prices or write data.

**Current limitation:** direct cloud requests may return no Amazon buy box, or store HTTP 403/404. The worker deliberately fails closed. This does not mean the store is necessarily out of stock. A browser or an authorized store feed is needed before claiming continuous verified-price coverage; no paid proxy is enabled.

## Manual Hepsiburada entries
Insert through the server/admin connection into `homepage_manual_deals`: title, optional brand/image_url, merchant_slug='hepsiburada', the normal product_url, the owner's full affiliate_url, and an explicit expires_at. Do not insert a guessed price. The worker checks the normal product page, and outbound clicks use the full affiliate_url. No public write or admin UI is exposed.

## Checks
From the repository root:
`node --experimental-strip-types --test tests/test_homepage.mjs`

The suite covers freshness, affiliate preservation, host restrictions, manual links, Turkish price parsing, mismatched visible/schema prices, membership-only prices, stock evidence and discovery fallback.

## Social sharing links
New social captions use the Firsatci /f/[code]?s=channel route. The URL-safe code packs the exact published candidate and offer UUIDs; it contains no credentials or external destination. The browser follows the existing Supabase click tracker, which retains the real visitor IP, user agent, navigation signals, bot classification, source channel and original affiliate URL. The website does not proxy or count an extra click. HEAD probes create no events. Social links are independent of homepage price freshness, and previously published Supabase links remain valid. Instagram recovery recognizes both formats.

## Yerel ana sayfa fiyat kontrolü (9 Ekim 2026)
Windows görevi `Firsatci Homepage Prices`: her gün 10:00–23:30, 30 dakikada bir.
PC uyanık ve kullanıcı oturumu açık olmalıdır; ekran kilitli/kapalı olabilir.
Codex uygulamasının açık olması gerekmez. Kurulum uyku/güç ayarlarını değiştirmez.
Görev kaçırılan gece saatlerini telafi etmez ve aynı anda ikinci çalışma açmaz.

- `refresh_homepage.py` tüm aktif aday ve manuel ürünleri üç paralel kontrolle dolaşır. Zaman bütçesi dolarsa kalanlar sonraki kontrolde öncelik alır.
- Üç kontrol paraleldir; aynı mağazaya kontrol istekleri sırayla yapılır.
- Doğrudan erişim yetmezse mevcut Chromium ile normal ürün sayfası okunur.
- Ortak `homepage-refresh/price.mjs` fiyat, ürün kimliği, stok, minimum adet ve kupon kurallarını uygular.
- Alış fiyatı tek başına doğrulandıysa fiyat gösterilir; rakip karşılaştırması doğrulanmadan indirim rozeti verilmez.
- Altı saati geçen doğrulanmış fiyat fırsat vitrininden çıkar; günlük arama fiyatı katalogda tarihli geçmiş kayıt olarak kalır. Bulut kontrolü 55 dakikadan yeni yerel fiyatı ezmez.
- Tekrar kurulum: `powershell -File install_homepage_schedule.ps1`.
- Salt ön izleme: `.venv\\Scripts\\python.exe refresh_homepage.py --limit 6`.
- Son sonuç: `logs/homepage-refresh-last.json`; görev çıktıları: `logs/homepage-*.log`.
- Sosyal yayın kuyruğu ve offers/price_history bu kontrol tarafından değiştirilmez.

## Domain raporu
Ana sayfa görünürken `/api/visit` tek sinyal gönderir. Sayfa yenileme nedeniyle tekrar eden
istekler günlük tekilleştirilir. `/urun` ve `/go` yönlendirmeleri mağazaya gidişi ayrı kaydeder.
HEAD ve bilinen bot/ön yükleme istekleri site toplamına alınmaz.
Ham IP/çerez/tam referer saklanmaz; günlük değişen sunucu HMAC özeti kullanılır.
Sayaçlar kişi veya resmi mağaza satış/tıklama raporu değildir.
Sosyal `/f` linkleri mevcut deal-click ölçümünden gelir; site ziyaretine eklenmez.
`get_click_report_v3` mevcut sosyal rapora ayrı website toplamlarını ekler.
Günlük/haftalık rapor ve Telegram /rapor yeni biçimi kullanır.
Ölçüm yayın tarihinden itibaren başlar; eski site ziyaretleri geri üretilemez.
Rapor işlevi özel Vault anahtarıyla çağrılır; Reels dosyası silmez.

## Full catalogue and product pages

Apply supabase/website_catalogue.sql and supabase/website_market.sql with the database migration tool. All RPCs and purchase checks are service-role-only; no public database grants are added.

The home lists every active approved candidate, with 24 cards per UI page, title/brand search, category and store filters. Categories use existing category labels plus conservative title rules; unknown products stay in Other. Category assignment is a display aid and never changes matching or collectors.

/urun-detay/[id] shows approved matching offers, recorded scan prices with timestamps, and daily history. Only a fresh purchase-price snapshot is labeled current. The history reads existing price_history, takes the last in-stock record per offer per Istanbul day, and does not fill missing days or write half-hour checks. Offers with a different known GTIN, color, size or capacity are excluded from the detail comparison. /magaza/[id]?offer=... validates membership and redirects to the original affiliate URL with website outbound tracking.

## Official brochures

/brosurler and the homepage shortcut link to official BİM, A101, ŞOK and Migros sources. Server-side source fetches revalidate hourly and do not require the PC to stay awake. Dated past campaigns are filtered out; current and near-future brochures are distinguished. A source with unavailable or unparseable dates uses its official landing page without an invented date. Only observed official images/PDF links are shown, and brochure links have no invented affiliate attribution.

## Catalogue verification

Run node --experimental-strip-types --test tests/test_homepage.mjs tests/market-price.test.mjs tests/brochures.test.mjs tests/website_catalogue.test.mjs tests/branded_links.test.mjs tests/site_traffic.test.mjs. The SQL suite uses QUEUE_SQL_TEST_RUNTIME pointing to a local PGlite test runtime. It checks approved variant identity, full catalogue pagination, purchase-price fallback, daily history, out-of-order observations, newer stock evidence, and private permissions.
