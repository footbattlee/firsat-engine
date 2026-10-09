import type {Metadata} from "next";
import {notFound} from "next/navigation";
import Link from "next/link";
import {getProductData,getSnapshot,toDeal} from "../../../lib/deals";
import {validListingId} from "../../../lib/policy";
import {SiteHeader,SiteFooter} from "../../site-header";
import {DealImage} from "../../deal-image";
import {PriceHistory} from "../../price-history";
import {LivePrices} from "../../live-prices";
export const dynamic="force-dynamic";
const money=new Intl.NumberFormat("tr-TR",{style:"currency",currency:"TRY"});
const time=new Intl.DateTimeFormat("tr-TR",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",timeZone:"Europe/Istanbul"});
export async function generateMetadata({params}:{params:Promise<{id:string}>}):Promise<Metadata>{
 const {id}=await params;if(!validListingId(id))return {title:"Ürün bulunamadı"};
 const row=await getSnapshot(id);
 return row?{title:String(row.title)+" | Fırsatcı",description:"Mağaza tekliflerini ve günlük fiyat geçmişini incele.",alternates:{canonical:"/urun-detay/"+id}}:{title:"Ürün bulunamadı"};
}
export default async function Product({params}:{params:Promise<{id:string}>}){
 const {id}=await params;if(!validListingId(id))notFound();
 const {row,offers,history}=await getProductData(id);if(!row)notFound();
 const deal=toDeal(row);
 return <main><LivePrices/><SiteHeader/><div className="shell productDetail">
 <nav className="breadcrumbs" aria-label="Sayfa yolu"><Link href="/">Ana sayfa</Link><span>/</span><Link href={"/?kategori="+deal.category+"#firsatlar"}>{deal.categoryName}</Link><span>/</span><span>Ürün fiyatları</span></nav>
 <section className="detailHero"><div className="detailVisual"><DealImage src={deal.imageUrl} title={deal.title} hero/></div><div className="detailIntro"><span className="eyebrow">{deal.brand||deal.categoryName}</span><h1>{deal.title}</h1>
 {deal.price!==null?<><span className="currentLabel">✓ Güncel fiyatı kontrol edildi</span><div className="detailPrice">{money.format(deal.price)}</div><p className="detailMuted">{deal.merchant} · Kontrol: {time.format(new Date(deal.checkedAt!))}</p></>:<><div className="detailPrice">Güncel fiyat mağazada</div><p className="detailMuted">Güncel satın alma fiyatını henüz doğrulayamadık. Aşağıdaki arama kayıtları güncel fiyat garantisi değildir.</p></>}
 {deal.gapPercent!==null?<p className="detailAdvantage">{deal.competitorMerchant}’a göre %{deal.gapPercent.toFixed(2)} daha ucuz <small>Bu oran ürünün eski fiyatına göre indirim değildir.</small></p>:null}
 <a className="primaryCta" href={deal.href} target="_blank" rel="nofollow sponsored noopener">{deal.merchant}’da gör ↗</a><a className="historyAnchor" href="#fiyat-gecmisi">Fiyat geçmişine bak ↓</a></div></section>
 <section className="detailPanel"><div className="sectionHead"><div><span className="eyebrow">AYNI ÜRÜNÜN TEKLİFLERİ</span><h2>Mağaza fiyatları <span className="count">{offers.length||1}</span></h2></div></div>
 <p className="detailMuted">Sadece onaylı ürün eşleşmeleri gösterilir. “Son arama kaydı” yazan fiyatlar belirtilen tarihte kaydedilmiştir; güncel fiyat ve stok mağazada değişmiş olabilir. Kargo, üyelik ve kupon koşulları ayrıca kontrol edilmelidir.</p>
 <div className="offerRows">{offers.length?offers.map(o=>{
 const cheapCurrent=o.id===String(row.offer_id)&&deal.price!==null;
 const rivalCurrent=o.id===String(row.competitor_offer_id)&&deal.competitorPrice!==null;
 const current=cheapCurrent||rivalCurrent;
 const currentPrice=cheapCurrent?deal.price:deal.competitorPrice;
 const recorded=Number(o.price)>0&&o.checked_at&&Date.parse(o.checked_at)<=Date.now();
 return <article className={"offerRow "+(current?"current":"")} key={o.id}><div><strong>{o.merchant_name}</strong>{o.seller?<small>Satıcı: {o.seller}</small>:null}<small>{current?"Güncel fiyat kontrolü":o.in_stock===false?"Son kayıtta stok yok":"Son arama kaydı"}{(current?deal.checkedAt:o.checked_at)?" · "+time.format(new Date((current?deal.checkedAt:o.checked_at)!)):""}</small></div>
 <div className="offerPrice">{current?money.format(currentPrice!):recorded?money.format(Number(o.price)):"Fiyat mağazada"}<small>{current?"Güncel kontrol edilen fiyat":"Geçmiş arama kaydı"}</small></div>
 <a href={"/magaza/"+id+"?offer="+o.id} target="_blank" rel="nofollow sponsored noopener">Mağazaya git ↗</a></article>;
 }):<article className="offerRow"><div><strong>{deal.merchant}</strong><small>Manuel eklenen mağaza bağlantısı</small></div><div className="offerPrice">{deal.price!==null?money.format(deal.price):"Fiyat mağazada"}</div><a href={deal.href} target="_blank" rel="nofollow sponsored noopener">Mağazaya git ↗</a></article>}</div></section>
 <PriceHistory history={history} offers={offers} defaultOffer={String(row.offer_id||"")}/>
 <p className="detailMuted">Fırsatcı alışverişin tamamlandığı mağaza değildir. Bağlantı gelir ortaklığı içeriyorsa mağazaya geçişte korunur.</p>
 </div><SiteFooter/></main>;
}
