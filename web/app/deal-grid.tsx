"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Deal } from "../lib/deals";
import { DealImage } from "./deal-image";
const money = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" });
const time = new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Istanbul" });
export function DealGrid({ deals }: { deals: Deal[] }) {
 const [query, setQuery] = useState(""), [store, setStore] = useState("all"), [sort, setSort] = useState("recent");
 const router = useRouter();
 useEffect(() => {
  const refresh = () => { if (document.visibilityState === "visible") router.refresh(); };
  const timer = window.setInterval(refresh, 60000);
  document.addEventListener("visibilitychange", refresh);
  return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", refresh); };
 }, [router]);
 const stores = useMemo(() => [...new Map(deals.map(d => [d.merchantSlug, d.merchant])).entries()], [deals]);
 const shown = useMemo(() => deals.filter(d => (store === "all" || store === d.merchantSlug) && (d.title + " " + d.brand).toLocaleLowerCase("tr").includes(query.toLocaleLowerCase("tr")))
  .sort((a,b) => sort === "price" ? (a.price ?? Infinity)-(b.price ?? Infinity) : sort === "gap" ? (b.gapPercent || 0)-(a.gapPercent || 0) : Date.parse(b.checkedAt || "1970-01-01")-Date.parse(a.checkedAt || "1970-01-01")), [deals, query, store, sort]);
 return <>
  <div className="tools">
   <label className="search"><span aria-hidden="true">⌕</span><input aria-label="Fırsatlarda ürün ara" placeholder="Ne arıyorsun?" value={query} onChange={e => setQuery(e.target.value)} /></label>
   <label className="sortLabel"><span>Sırala</span><select aria-label="Fırsatları sırala" value={sort} onChange={e => setSort(e.target.value)}><option value="recent">Son kontrol edilen</option><option value="gap">En yüksek fiyat avantajı</option><option value="price">En düşük fiyat</option></select></label>
  </div>
  <div className="storeFilters" role="group" aria-label="Mağazaya göre filtrele">
   <button className={store === "all" ? "selected" : ""} aria-pressed={store === "all"} onClick={() => setStore("all")}>Tüm mağazalar <span>{deals.length}</span></button>
   {stores.map(([slug,name]) => <button key={slug} className={store === slug ? "selected" : ""} aria-pressed={store === slug} onClick={() => setStore(slug)}>{name}</button>)}
  </div>
  {shown.length ? <div className="grid">{shown.map(deal => <article className="dealCard" key={deal.id}>
   <div className="productVisual"><DealImage key={deal.imageUrl} src={deal.imageUrl} title={deal.title} />
    <span className="cardBadge">{deal.gapPercent !== null ? "%" + deal.gapPercent.toFixed(0) + " daha ucuz" : deal.price !== null ? "Fiyat kontrol edildi" : "Fiyat mağazada"}</span>
   </div>
   <div className="cardBody"><div className={"merchant " + deal.merchantSlug}><span aria-hidden="true">●</span>{deal.merchant}</div>
    <h3>{deal.title}</h3>
    {deal.price !== null ? <div className="price">{money.format(deal.price)}</div> : <div className="storePrice">Fiyatı mağazada gör</div>}
    {deal.competitorPrice !== null ? <p className="rival">{deal.competitorMerchant}: <b>{money.format(deal.competitorPrice)}</b></p> : <p className="rival">{deal.price !== null ? "Güncel mağaza fiyatı; indirim karşılaştırması doğrulanmadı." : "Güncel fiyatı henüz doğrulayamadık."}</p>}
    <a className="dealCta" href={deal.href} target="_blank" rel="nofollow sponsored noopener">{deal.merchant}’da gör <span aria-hidden="true">↗</span></a>
    <div className="checked">{deal.checkedAt ? <><span aria-hidden="true">✓</span> Kontrol: <time dateTime={deal.checkedAt}>{time.format(new Date(deal.checkedAt))}</time></> : "Fiyat ve stok için mağazayı kontrol et."}</div>
   </div>
  </article>)}</div> : <div className="emptyState"><div aria-hidden="true">✦</div><h3>{deals.length ? "Bu aramada fırsat bulunamadı." : "Güncel fırsatları kontrol ediyoruz."}</h3><p>{deals.length ? "Başka bir ürün adı veya mağaza deneyebilirsin." : "Fiyatı doğrulanmadan bir ürünü burada listelemiyoruz. Yeni doğrulanan fırsatlar otomatik olarak bu alana gelir."}</p>{deals.length > 0 && <button onClick={() => {setQuery("");setStore("all");}}>Tüm fırsatları göster</button>}</div>}
 </>;
}
