import { getDeals } from "../lib/deals";
import { DealGrid } from "./deal-grid";
import { DealImage } from "./deal-image";
export const dynamic = "force-dynamic";
const money = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });
export default async function Home() {
 let deals = [] as Awaited<ReturnType<typeof getDeals>>;
 let unavailable = false;
 try { deals = await getDeals(); } catch { unavailable = true; }
 const featured = deals.find(d => d.price !== null && d.imageUrl && d.affiliate) || deals.find(d => d.price !== null && d.imageUrl);
 return <main>
  <header className="siteHeader"><div className="shell headerInner">
   <a className="logo" href="/" aria-label="Fırsatcı ana sayfa"><span className="logoSymbol" aria-hidden="true">f</span>fırsatcı<span className="logoDot">.</span></a>
   <nav aria-label="Ana menü"><a href="#firsatlar">Günün fırsatları</a><a href="#nasil">Nasıl çalışır?</a></nav>
   <a className="headerCta" href="#firsatlar">Fırsatları keşfet <span aria-hidden="true">↗</span></a>
  </div></header>
  <section className="hero"><div className="shell heroLayout">
   <div className="heroCopy"><div className="eyebrow"><span aria-hidden="true">✦</span> İYİ FİYATIN PEŞİNDE</div>
    <h1>İyi fiyatı bul.<br /><span>Fırsatı yakala.</span></h1>
    <p>Mağazalar arasında kaybolma. Ürünleri ve doğrulanan fiyat avantajlarını keşfet, alışverişini doğrudan mağazada tamamla.</p>
    <div className="heroActions"><a className="primaryCta" href="#firsatlar">Ürünleri keşfet <span aria-hidden="true">↗</span></a><span className="heroNote">Türkiye’nin sevilen mağazalarından</span></div>
    <div className="heroStores"><span>Amazon</span><span>Trendyol</span><span>Hepsiburada</span><span>+ diğerleri</span></div>
   </div>
   {featured ? <div className="heroFeature"><div className="featureHeader"><span>ŞİMDİ KEŞFET</span><span className="liveLabel">✓ Fiyatı kontrol edildi</span></div><div className="featureVisual"><DealImage key={featured.imageUrl} src={featured.imageUrl} title={featured.title} hero /></div><div className="featureBottom"><div><small>{featured.merchant}</small><h2>{featured.title}</h2></div><div className="featurePrice">{money.format(featured.price!)}</div></div><a href={featured.href} className="featureLink" target="_blank" rel="nofollow sponsored noopener">{featured.merchant}’da gör <span aria-hidden="true">↗</span></a></div>
    : <div className="heroPoster"><div className="posterCircle" aria-hidden="true">↘</div><span>AKILLI ALIŞVERİŞİN<br />KÜÇÜK BİR KISAYOLU.</span><strong>Fırsatı keşfet.<br />İyi fiyatı yakala<span>.</span></strong><p>Açık fiyat bilgisi. Açık karşılaştırma.<br />Doğrudan mağazaya bağlantı.</p><div className="posterStamp" aria-hidden="true">fırsatcı / iyi fiyat</div></div>}
  </div></section>
  <div className="shell trustStrip"><div><span aria-hidden="true">✓</span><p><b>Kontrol zamanı açık</b><small>Doğrulanan fiyatlarda son kontrol zamanı</small></p></div><div><span aria-hidden="true">↗</span><p><b>Doğrudan mağazaya</b><small>Alışveriş ilgili mağazada tamamlanır</small></p></div><div><span aria-hidden="true">≋</span><p><b>Karşılaştırma net</b><small>Rakip fiyatı, eski fiyat değildir</small></p></div></div>
  <section className="shell dealsSection" id="firsatlar"><div className="sectionHead"><div><span className="eyebrow">FİYAT AVANTAJINI KEŞFET</span><h2>Ürünleri keşfet<span className="count">{deals.length}</span></h2></div><p>Doğrulanan fiyatlar burada. Diğer ürünlerin fiyatını mağazada gör.</p></div>
   {unavailable && <p className="notice" role="status">Fırsat listesine şu anda erişemiyoruz. Kısa süre sonra tekrar deneyebilirsin.</p>}
   <DealGrid deals={deals} />
  </section>
  <section className="howSection" id="nasil"><div className="shell"><div className="sectionHead"><div><span className="eyebrow">FIRSATCI NASIL ÇALIŞIR?</span><h2>Üç adımda daha iyi fiyat.</h2></div></div><div className="howGrid"><div><span>01 / KEŞFET</span><h3>İlgini çeken ürünü bul.</h3><p>Mağazaya göre filtrele, fiyatları karşılaştır. Gösterilen avantaj, adı belirtilen rakip mağazaya göredir.</p></div><div><span>02 / KONTROL ET</span><h3>Fiyatın ne zaman kontrol edildiğini gör.</h3><p>Fiyatı doğrulanamayan ürünlerde rakam göstermiyoruz. Son kontrolü bir saati geçen fiyatlar gizlenir.</p></div><div><span>03 / MAĞAZAYA GİT</span><h3>Alışverişini mağazada tamamla.</h3><p>Ödeme, teslimat ve iade ilgili mağazada yapılır. Satın almadan önce son fiyatı ve koşulları kontrol et.</p></div></div></div></section>
  <footer className="siteFooter"><div className="shell"><a className="logo" href="/"><span className="logoSymbol" aria-hidden="true">f</span>fırsatcı<span className="logoDot">.</span></a><p>İyi fiyatın peşinde.</p><div className="footerBottom"><span>© {new Date().getFullYear()} Fırsatcı</span><p>Bazı bağlantılar gelir ortaklığı bağlantısıdır. Fiyatlar ve stok değişebilir. Üyelik veya kupon gerektiren fiyatlar, herkes için geçerli fiyat gibi sunulmaz.</p></div></div></footer>
 </main>;
}
