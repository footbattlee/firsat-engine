# Bulutta otomatik Instagram kuyruğu

Supabase publication-queue işlevi ve PostgreSQL Cron, bilgisayar kapalıyken çalışır. Arama saatine bağımlı değildir. deal_candidates tablosundaki INSERT/UPDATE tetikleyicisi yeni adayları kalıcı publication_queue tablosuna ekler. Yalnızca belirlenen başlangıçtan sonra yapılan ve tamamlanan taramaların adayları sıraya girer; eski aramalar otomatik yayın dışında tutulur. Aynı aday/kanonik ürün tekrarlanmaz. Instagram yayını başarılı olan ürün yeniden paylaşılmaz.

Türkiye saatiyle 10.00–23.30 arası yarım saatlik 28 yayın noktası vardır. Kaçırılan saatler sonradan topluca çalıştırılmaz. Bir saat diliminde en fazla bir Instagram gönderisi yayınlanır. Kuyruk boşsa gönderi olmaz.

Yayın, tamamlanan taramanın kayıtlı fiyatlarıyla hazırlanır. Kullanıcının onayıyla yayın sırasında canlı mağaza erişimi ve stok kontrolü yapılmaz. Mevcut onaylı ürün eşleşmesi, iki farklı mağaza, pozitif fiyatlar ve avantaj eşiği DB kayıtları üzerinden kontrol edilir. Avantaj eşiği altındaki, şüpheli veya görseli hazırlanamayan ürün ertelenir. Ertelenen ürün sıranın arkasına alınır, diğer ürünleri engellemez.

Gönderi ve 1080x1920 story görselleri tamamlanan taramada kaydedilen fiyatlarla bulutta hazırlanır. Instagram başarıyla yayınlandıktan sonra story.png, Telegram story/admin hedefindeki sohbete belge olarak ve ürün bağlantısıyla teslim edilir. Story otomatik Instagram yayını değildir. Reels seçimi mevcut Telegram REELS PAYLAŞ düğmesinde kullanıcıdadır. Facebook ve Telegram kanalına otomatik yayın bu kuyruk kapsamında yoktur.

Kuyruk tablolarında RLS açıktır; anonim ve normal kullanıcı erişimi yoktur. İşlev servis anahtarı veya Vault'ta tutulan özel zamanlayıcı anahtarıyla çağrılır. Instagram yayın sonucu belirsiz kalırsa ürün held durumuna alınır; tekrar gönderilmez. Story gönderiminde belirsiz sonuç da tekrar gönderilmez, kayıt incelenmelidir.

Kontrol: public.publication_queue.state, last_error ve public.publication_slots. Durdurma: publication_queue_settings.enabled=false. Cron adı instagram-publication-half-hour. Kaynak SQL supabase/cloud_publication_queue.sql ve zamanlayıcı SQL supabase/schedule_publication_queue.sql dosyalarındadır.

Yayın yapmayan test: publication-queue endpointine servis yetkisiyle POST {"dry_run":true}. Görsel testi POST {"mode":"render-test"}. Bu testler gerçek gönderi oluşturmaz. Node testleri: node --test tests/cloud_queue.test.ts.

Fırsat keşfinde DEAL_COMPETITOR_WORKERS varsayılan 3 ve en fazla 3'tür. Aynı mağazadaki ürünler sırayla aranır; farklı mağazalar paralel aranır. Normal kategori taramasının COLLECTOR_WORKERS=3 ayarı korunur.

## Geçerli tarama sınırı

4 Ekim 2026 20.53.03 öncesi aramalar otomatik yayın dışına alınmıştır. Minimum yayın zamanı 5 Ekim 2026 10.00 Türkiye saatidir. deal_engine, PIPELINE_STARTED_AT değeriyle publication_scan_batches kaydı açar; aday satırlarına scan_started_at yazar ve analiz başarıyla tamamlanınca complete_publication_scan RPC'sini çağırır. Kuyruk, yalnızca tamamlanmış taramaların adaylarını seçer. Eski aday aynı yeni taramada tekrar geçerli bulunursa yeni tarama etiketiyle yeniden kuyruğa alınabilir; yayımlanmış aday yeniden paylaşılmaz.

Tarama ayrımı ve başlangıç engelinin SQL'i supabase/publication_queue_scan_scope.sql içindedir. Mağaza erişim engelleri yayın aşamasını engellemez. Görsel/Instagram API hataları veya boş kuyruk durumunda o saat için gönderi oluşmayabilir. Cloud connection-test tanısı sadece servis yetkisiyle çalışır; otomatik yayından bağımsızdır, fiyat kontrol eder ve hiç yayın yapmaz.

## Yayın kontrolü tercihi

Kullanıcı 5 Ekim başlangıcı için, yayın öncesi canlı mağaza fiyat/stok erişiminin kaldırılmasını açıkça onayladı. Yayın verisi tamamlanan taramanın deal_candidates fiyat snapshot'ından alınır; mağaza sitesi yayın anında çağrılmaz. Ürün eşleşmesi, iki farklı mağaza, fiyat matematiği ve avantaj eşiği DB kayıtları üzerinden kontrol edilir. Görsel indirme ve Instagram API erişimi yayının teknik gereğidir ve devam eder. Gönderi açıklaması fiyatın son taramaya ait olduğunu ve fiyat/stokun değişebileceğini belirtir. connection-test, yalnızca elle tanı amacıyla kullanılabilir; otomatik yayın akışında değildir.
