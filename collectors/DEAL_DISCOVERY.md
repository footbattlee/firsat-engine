# Fırsat sayfalarından ürün keşfi

Pipeline önce Amazon, Trendyol ve Hepsiburada fırsat sayfalarını tarar. Her kaynak ürün diğer beş mağazada aranır; categories.json veya önceden DB içinde bulunması gerekmez. Ardından mevcut kategori taraması, eşleştirme, fiyat yenileme, fırsat analizi ve yönetici onay akışı çalışır.

Trendyol: /flas-indirimler ve ana sayfadaki Avantajlı Ürünler bağlantısı.
Hepsiburada: /gunun-firsati-teklifi ve /kampanyalar/en-avantajli-fiyatlar.

Kaynak fiyatı ürün detayındaki tek TRY Offer ve açık stok bilgisiyle doğrulanır. Vitrin kuponu, üyelik indirimi ve çoklu alım tutarı doğrudan fiyat yerine kullanılmaz. Bilinen yenilenmiş/ikinci el/teşhir ürünleri elenir. Bulunan rakipler kimlik ve varyant eşleşmesi ve canlı detay fiyatı doğrulanınca kaydedilir. Eşleşme yoksa ürün otomatik fırsat sayılmaz.

Varsayılanlar: TRENDYOL_DEALS_ENABLED=1, HEPSIBURADA_DEALS_ENABLED=1. Her biri *_DEALS_LIMIT=30 ile sınırlandırılır. DEAL_COMPETITOR_TIMEOUT=120 (arama başına saniye), DEAL_COMPETITOR_SEARCH_LIMIT=5. Aramalar süreyi artırır. Amazon mevcut AMAZON_* ayarlarını kullanır.

Kayıtsız kontrol: python collectors/trendyol_deals.py --dry-run --find-competitors --limit 1 (Hepsiburada için hepsiburada_deals.py). Kuru test DB yazmaz; reports altında sonuç raporu bırakır. Hiç doğrulanmış kaynak ürün bulunamazsa code=4; pipeline diğer kaynaklara devam eder.
