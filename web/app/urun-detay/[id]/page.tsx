import type {Metadata} from "next";
import {notFound} from "next/navigation";
import Link from "next/link";
import {getProductData,getSnapshot,toDeal} from "../../../lib/deals";
import {validListingId} from "../../../lib/policy";
import {recent,PURCHASE_CHECK_AGE_MS} from "../../../lib/market-price";
import {SiteHeader,SiteFooter} from "../../site-header";
import {DealImage} from "../../deal-image";
import {PriceHistory} from "../../price-history";
import {LivePrices} from "../../live-prices";
export const dynamic="force-dynamic";
const money=new Intl.NumberFormat("tr-TR",{style:"currency",currency:"TRY"});
const time=new Intl.DateTimeFormat("tr-TR",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",timeZone:"Europe/Istanbul"});
export async function generateMetadata({params}:{params:Promise<{id:string}>}):Promise<Metadata>{
 const {id}=await params;if(!validListingId(id))return {title:"Ürün bulunamadı"};
 const row=await getSnapshot(id);return row?{title:String(row.title)+" | Fırsatcı",description:"Mağaza tekliflerini ve günlük fiyat geçmişini incele.",alternates:{canonical:"/urun-detay/"+id}}:{title:"Ürün bulunamadı"};
}
export default async function Product({params}:{params:Promise<{id:string}>}){
 const {id}=await params;if(!validListingId(id))notFound();
 const {row,offers,history}=await getProductData(id);if(!row)notFound();
 const deal=toDeal(row);
 return <main><LivePrices/><SiteHeader/><div className="shell productDetail">
 <nav className="breadcrumbs" aria-label="Sayfa yolu"><Link href="/">Ana sayfa</Link><span>/</span><Link href={"/?kategori="+deal.category+"&secim=all#firsatlar"}>{deal.categoryName}</Link><span>/</span><span>Ürün fiyatları</span></nav>
 <section className="detailHero"><div className="detailVisual"><DealImage src={deal.imageUrl} title={deal.title} hero/></div><div className="detailIntro"><span className="eyebrow">{deal.brand||deal.categoryName}</span><h1>{deal.title}</h1>
 {deal.price!==null?<><span className="currentLabel">✓ Kontrol edilen en düşük teklif</span>{deal.dropPercent!==null?<div className="previousPrice"><s>{money.format(deal.oldPrice!)}</s><span>Önceki günlük fiyat · {time.format(new Date(deal.oldCheckedAt!))}</span></div>:null}<div className="detailPrice">{money.format(deal.price)}</div><p className="detailMuted">{deal.merchant} · Kontrol: {time.format(new Date(deal.checkedAt!))}<br/>{deal.offerCount} onaylı teklif arasındaki doğrulanmış fiyatlar karşılaştırıldı.</p></>:<><span className="recordedPriceLabel">Son kaydedilen arama fiyatı</span><div className="detailPrice">{deal.recordedPrice!==null?money.format(deal.recordedPrice):"Henüz fiyat kaydı yok"}</div><p className="detailMuted">{deal.recordedPrice!==null?deal.recordedMerchant+" · "+time.format(new Date(deal.recordedCheckedAt!)):"Mağaza teklifleri ve yeni fiyat kontrolleri burada görünecek."}<br/>Bu geçmiş kayıt güncel satın alma fiyatı değildir.</p></>}
 {deal.dropPercent!==null?<p className="detailAdvantage">%{deal.dropPercent.toFixed(2)} fiyat düştü · {money.format(deal.savings!)} fark<small>Aynı mağaza teklifinin önceki günlük kaydıyla karşılaştırıldı.</small></p>:null}
 {deal.gapPercent!==null?<p className="detailAdvantage competitorAdvantage">{deal.competitorMerchant}’a göre %{deal.gapPercent.toFixed(2)} daha ucuz <small>Rakip teklif: {money.format(deal.competitorPrice!)}. Bu oran eski fiyata göre indirim değildir.</small></p>:null}
 <a className="primaryCta" href={deal.href} target="_blank" rel="nofollow sponsored noopener">{deal.merchant}’da satın al ↗</a><a className="historyAnchor" href="#fiyat-gecmisi">Fiyat geçmişine bak ↓</a></div></section>
 <section className="detailPanel"><div className="sectionHead"><div><span className="eyebrow">AYNI ÜRÜNÜN TEKLİFLERİ</span><h2>Mağaza fiyatları <span className="count">{offers.length||1}</span></h2></div></div>
 <p className="detailMuted">Kontrol edilen fiyatlar en fazla 6 saatliktir; her teklifin tarihi aşağıda gösterilir. Geçmiş arama kayıtları ayrıca belirtilir. Kargo tutarı henüz doğrulanmıyor; fiyatlara kargo dahil olduğu varsayılmaz. Kupon ve üyelik fiyatları standart fiyatla karıştırılmaz.</p>
 <div className="offerRows">{offers.length?offers.map(o=>{
 const current=Number(o.live_price)>0&&recent(o.live_checked_at,PURCHASE_CHECK_AGE_MS);
 const recorded=Number(o.price)>0&&o.checked_at&&Date.parse(o.checked_at)<=Date.now();
 const best=current&&o.id===String(row.offer_id);
 const checked=current?o.live_checked_at:o.checked_at;
 return <article className={"offerRow "+(best?"current":"")} key={o.id}><div><strong>{o.merchant_name}{best?<span className="bestOffer">En düşük doğrulanan</span>:null}</strong>{o.seller?<small>Satıcı: {o.seller}</small>:null}<small>{current?"Fiyat kontrolü":o.in_stock===false?"Son kayıtta stok yok":"Son arama kaydı"}{checked?" · "+time.format(new Date(checked)):""}</small><small>Kargo: mağazada kontrol et</small></div>
 <div className="offerPrice">{current?money.format(Number(o.live_price)):recorded?money.format(Number(o.price)):"Henüz fiyat kaydı yok"}<small>{current?"Kontrol edilen fiyat":"Geçmiş arama kaydı"}</small></div><a href={"/magaza/"+id+"?offer="+o.id} target="_blank" rel="nofollow sponsored noopener">Mağazaya git ↗</a></article>;
 }):<article className="offerRow"><div><strong>{deal.merchant}</strong><small>Manuel eklenen mağaza bağlantısı</small></div><div className="offerPrice">{deal.price!==null?money.format(deal.price):"Henüz fiyat kaydı yok"}</div><a href={deal.href} target="_blank" rel="nofollow sponsored noopener">Mağazaya git ↗</a></article>}</div></section>
 <PriceHistory history={history} offers={offers} defaultOffer={String(row.offer_id||"")}/>
 <p className="detailMuted">Son fiyat, stok, satıcı ve kargo koşulları mağazada geçerlidir. Gelir ortaklığı bağlantısı mağazaya geçişte korunur.</p></div><SiteFooter/></main>;
}