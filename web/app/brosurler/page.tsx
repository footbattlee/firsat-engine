import type {Metadata} from "next";
import Link from "next/link";
import {getBrochures,BROCHURE_STORES} from "../../lib/brochures";
import {SiteHeader,SiteFooter} from "../site-header";
import {BrochureCards} from "../brochure-cards";
export const dynamic="force-dynamic";
export const metadata:Metadata={title:"İndirim Broşürleri | Fırsatcı",description:"BİM, A101, ŞOK ve Migros resmi indirim broşürlerini ve aktüel kataloglarını keşfet.",alternates:{canonical:"/brosurler"}};
export default async function Brochures(){
 const brochures=await getBrochures();
 return <main><SiteHeader/><section className="brochureHero"><div className="shell"><nav className="breadcrumbs"><Link href="/">Ana sayfa</Link><span>/</span><span>İndirim broşürleri</span></nav><span className="eyebrow">HAFTALIK ALIŞVERİŞİNİ PLANLA</span><h1>İndirim broşürleri</h1><p>Marketlerin aktüel ürünlerini ve dönemsel kampanyalarını resmi kaynaklarından keşfet.</p></div></section>
 <section className="shell brochureSection"><BrochureCards brochures={brochures}/><p className="detailMuted">Broşürler mağazaların resmi sayfalarından saatte bir yenilenir. Tarihi doğrulanabilen kataloglar burada gösterilir; diğer mağazaların güncel broşürleri resmi bağlantıda açılır. Fiyat, stok ve bölgesel koşullar mağazada geçerlidir.</p>
 {brochures.length?<div className="detailPanel"><h2>Tarihli kataloglar</h2><div className="datedBrochures">{brochures.map(b=><a key={b.href} href={b.href} target="_blank" rel="noopener noreferrer"><strong>{b.name}</strong><span>{b.dateLabel}</span><span>İncele ↗</span></a>)}</div></div>:null}
 <div className="brochureSources"><h2>Resmi kaynaklar</h2>{BROCHURE_STORES.map(s=><a key={s.id} href={s.url} target="_blank" rel="noopener noreferrer">{s.name} ↗</a>)}</div></section><SiteFooter/></main>;
}
