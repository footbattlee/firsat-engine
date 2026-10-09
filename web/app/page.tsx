import { getDeals } from "../lib/deals";
import { DealGrid } from "./deal-grid";
import { VisitCounter } from "./visit-counter";
import { SiteHeader,SiteFooter } from "./site-header";
export const dynamic="force-dynamic";
export default async function Home({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}) {
 const initial=await searchParams;
 let deals=[] as Awaited<ReturnType<typeof getDeals>>,unavailable=false;
 try{deals=await getDeals();}catch{unavailable=true;}
 return <main><VisitCounter/><SiteHeader/>
 {unavailable?<div className="shell"><p className="notice" role="status">Ürün listesine şu anda erişemiyoruz. Kısa süre sonra tekrar deneyebilirsin.</p></div>:null}
 <DealGrid deals={deals} initial={initial}/>
 <section className="howSection" id="nasil"><div className="shell"><h2>Fırsatı bul, fiyatını karşılaştır.</h2>
 <div className="howGrid"><div><span>01 / KEŞFET</span><h3>Tüm ürünler elinin altında.</h3><p>Kategori, mağaza veya ürün adıyla ara. Tüm aktif fırsatlara sayfalar arasında erişebilirsin.</p></div>
 <div><span>02 / KARŞILAŞTIR</span><h3>Fiyatın tarihini gör.</h3><p>Ürünün mağaza tekliflerini ve günlük aramalarda kaydedilen fiyat geçmişini incele. Son kontrolü bir saati geçen fiyatı güncel fiyat olarak göstermiyoruz.</p></div>
 <div><span>03 / MAĞAZAYA GİT</span><h3>Alışverişini mağazada tamamla.</h3><p>Ürün sayfasından ilgili mağazaya geç. Son fiyatı, satıcıyı, kargoyu ve varsa kupon koşullarını satın almadan önce kontrol et.</p></div></div></div></section>
 <SiteFooter/></main>;
}
