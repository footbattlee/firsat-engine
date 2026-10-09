# Fırsatcı homepage

Run `pnpm install --ignore-scripts`, then `pnpm build` or `pnpm dev`.
Server-only environment: `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Never use a NEXT_PUBLIC service key.

## Price and link rules
- The homepage reads every active approved listing through private website_catalogue; prices still require a fresh homepage_deals snapshot.
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
- Bir saati geçen fiyat gizlenir. Bulut kontrolü 55 dakikadan yeni yerel fiyatı ezmez.
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

Apply supabase/website_catalogue.sql with the database migration tool. All three RPCs are service-role-only; no public database grants are added.

The home lists every active approved candidate, with 24 cards per UI page, title/brand search, category and store filters. Categories use existing category labels plus conservative title rules; unknown products stay in Other. Category assignment is a display aid and never changes matching or collectors.

/urun-detay/[id] shows approved matching offers, recorded scan prices with timestamps, and daily history. Only a fresh purchase-price snapshot is labeled current. The history reads existing price_history, takes the last in-stock record per offer per Istanbul day, and does not fill missing days or write half-hour checks. Offers with a different known GTIN, color, size or capacity are excluded from the detail comparison. /magaza/[id]?offer=... validates membership and redirects to the original affiliate URL with website outbound tracking.
