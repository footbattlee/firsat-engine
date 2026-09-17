import { getDeals } from "../lib/deals";

const money = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });

export default async function Home() {
  let deals = [] as Awaited<ReturnType<typeof getDeals>>;
  let error = "";
  try { deals = await getDeals(); } catch (e) { error = e instanceof Error ? e.message : "Veriler alınamadı"; }

  return (
    <main>
      <header className="hero">
        <div className="shell">
          <span className="eyebrow">PLAYFOOTBATTLE • FIRSAT</span>
          <h1>Gerçek fiyatları karşılaştır.<br />Fırsatı yakala.</h1>
          <p>Mağazalar arasındaki fiyat farklarını ve geçmiş fiyat hareketlerini tek yerde karşılaştırıyoruz.</p>
          <div className="stats">
            <div><strong>{deals.length}</strong><span>aktif fırsat</span></div>
            <div><strong>{deals.filter(d => d.verified).length}</strong><span>fiyat geçmişiyle doğrulandı</span></div>
          </div>
        </div>
      </header>

      <section className="shell content">
        <div className="sectionHead"><div><span className="eyebrow dark">GÜNCEL</span><h2>Fırsatlar</h2></div><p>Fiyatlar periyodik olarak kontrol edilir.</p></div>
        {error && <div className="notice">Veri bağlantısı henüz hazır değil: {error}</div>}
        {!error && deals.length === 0 && <div className="notice">Şu anda aktif fırsat bulunamadı. Yeni taramaları bekliyoruz.</div>}
        <div className="grid">
          {deals.map(deal => (
            <article className="card" key={deal.id}>
              <div className="badges"><span className="discount">%{deal.gapPercent.toFixed(0)} daha ucuz</span>{deal.verified && <span className="verified">✓ Doğrulandı</span>}</div>
              <div className="brand">{deal.brand || "FIRSAT"}</div>
              <h3>{deal.title}</h3>
              <div className="priceRow"><strong>{money.format(deal.price)}</strong><span>{money.format(deal.competitorPrice)}</span></div>
              <div className="compare"><b>{deal.merchant}</b><span>Rakip: {deal.competitorMerchant}</span></div>
              {deal.historyDropPercent > 0 && <p className="history">Geçmiş fiyata göre %{deal.historyDropPercent.toFixed(1)} düşüş görüldü.</p>}
              <a className="cta" href={deal.productUrl} target="_blank" rel="nofollow sponsored noopener">Mağazada Gör <span>→</span></a>
            </article>
          ))}
        </div>
        <footer>Fiyatlar değişebilir. Satın alma işlemi ilgili mağazada tamamlanır. Bazı bağlantılar gelir ortaklığı bağlantısı olabilir.</footer>
      </section>
    </main>
  );
}
