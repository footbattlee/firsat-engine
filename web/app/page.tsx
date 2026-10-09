import Link from "next/link";
import {Suspense} from "react";
import {getBrochures} from "../lib/brochures";
import {BrochureCards} from "./brochure-cards";
import { getDeals } from "../lib/deals";
import { DealGrid } from "./deal-grid";
import { VisitCounter } from "./visit-counter";
import { SiteHeader,SiteFooter } from "./site-header";
export const dynamic="force-dynamic";
async function BrochurePreview(){const brochures=await getBrochures();return <section className="shell brochureSection" id="brosurler"><div className="sectionHead"><div><span className="eyebrow">HAFTALIK KATALOGLAR</span><h2>İndirim broşürleri</h2></div><Link className="textLink" href="/brosurler">Tüm broşürleri incele ↗</Link></div><BrochureCards brochures={brochures}/></section>;}
export default async function Home({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}) {
 const initial=await searchParams;
 let deals=[] as Awaited<ReturnType<typeof getDeals>>,unavailable=false;
 try{deals=await getDeals();}catch{unavailable=true;}
 return <main><VisitCounter/><SiteHeader/>
 {unavailable?<div className="shell"><p className="notice" role="status">Ürün listesine şu anda erişemiyoruz. Kısa süre sonra tekrar deneyebilirsin.</p></div>:null}
 <DealGrid deals={deals} initial={initial}/>
 <Suspense fallback={<div className="shell brochureLoading">Resmi broşür kaynakları yükleniyor…</div>}><BrochurePreview/></Suspense>
 <section className="howSection" id="nasil"><div className="shell"><h2>Fırsatı bul, fiyatını karşılaştır.</h2>
 <div className="howGrid"><div><span>01 / KEŞFET</span><h3>Tüm ürünler elinin altında.</h3><p>Kategori, mağaza veya ürün adıyla ara. Tüm aktif ürünlere sayfalar arasında erişebilirsin.</p></div>
 <div><span>02 / KARŞILAŞTIR</span><h3>Fiyatın tarihini gör.</h3><p>Ürünün mağaza tekliflerini ve günlük aramalarda kaydedilen fiyat geçmişini incele. Kontrol edilen fiyatlar en fazla 6 saatliktir. Daha eski arama fiyatları tarihleriyle katalogda gösterilir.</p></div>
 <div><span>03 / MAĞAZAYA GİT</span><h3>Alışverişini mağazada tamamla.</h3><p>Ürün sayfasından ilgili mağazaya geç. Son fiyatı, satıcıyı, kargoyu ve varsa kupon koşullarını satın almadan önce kontrol et.</p></div></div></div></section>
 <SiteFooter/></main>;
}
