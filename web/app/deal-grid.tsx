"use client";
import {useEffect,useMemo,useState} from "react";
import {useRouter} from "next/navigation";
import Link from "next/link";
import type {Deal} from "../lib/deals";
import {CATEGORIES} from "../lib/categories";
import {DealImage} from "./deal-image";
import {CategoryIcon} from "./category-icon";
const money=new Intl.NumberFormat("tr-TR",{style:"currency",currency:"TRY"});
const time=new Intl.DateTimeFormat("tr-TR",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit",timeZone:"Europe/Istanbul"});
const PAGE_SIZE=24;
const MODES=[["opportunity","Günün fırsatları"],["priced","Kontrol edilen fiyatlar"],["drop","Fiyatı düşenler"],["rival","Rakipten ucuz"],["all","Tüm ürünler"]] as const;
const stringValue=(v:unknown)=>typeof v==="string"?v:"";
export function DealGrid({deals,initial={}}:{deals:Deal[];initial?:Record<string,unknown>}){
 const q0=stringValue(initial.q),store0=stringValue(initial.magaza)||"all",category0=stringValue(initial.kategori)||"all",sort0=stringValue(initial.sirala)||"advantage";
 const requested=stringValue(initial.secim);
 const mode0=requested==="verified"?"rival":MODES.some(([id])=>id===requested)?requested:category0!=="all"||q0?"all":"opportunity";
 const page0=Math.max(1,Number.parseInt(stringValue(initial.sayfa),10)||1);
 const [query,setQuery]=useState(q0),[store,setStore]=useState(store0),[category,setCategory]=useState(category0),[sort,setSort]=useState(sort0),[mode,setMode]=useState(mode0),[page,setPage]=useState(page0);
 // A same-page menu navigation supplies new filters without remounting the grid.
 useEffect(()=>{setQuery(q0);setStore(store0);setCategory(category0);setSort(sort0);setMode(mode0);setPage(page0);},[initial,q0,store0,category0,sort0,mode0,page0]);
 const router=useRouter();
 useEffect(()=>{const refresh=()=>{if(document.visibilityState==="visible")router.refresh();};const timer=window.setInterval(refresh,60000);document.addEventListener("visibilitychange",refresh);return()=>{window.clearInterval(timer);document.removeEventListener("visibilitychange",refresh);};},[router]);
 useEffect(()=>{const params=new URLSearchParams();if(query)params.set("q",query);if(store!=="all")params.set("magaza",store);if(category!=="all")params.set("kategori",category);if(sort!=="advantage")params.set("sirala",sort);if(mode!=="opportunity")params.set("secim",mode);if(page>1)params.set("sayfa",String(page));window.history.replaceState(null,"","/"+(params.size?"?"+params:"")+window.location.hash);},[query,store,category,sort,mode,page]);
 const stores=useMemo(()=>[...new Map(deals.map(d=>[d.merchantSlug,d.merchant])).entries()],[deals]);
 const counts=useMemo(()=>{const m=new Map<string,number>();for(const d of deals)m.set(d.category,(m.get(d.category)||0)+1);return m;},[deals]);
 const modeCount=(m:string)=>deals.filter(d=>m==="all"||m==="priced"&&d.price!==null||m==="drop"&&d.dropPercent!==null||m==="rival"&&d.gapPercent!==null||m==="opportunity"&&d.price!==null&&(d.dropPercent!==null||d.gapPercent!==null||d.manual)).length;
 const shown=useMemo(()=>deals.filter(d=>(store==="all"||d.merchantSlug===store)&&(category==="all"||d.category===category)&&
 (mode==="all"||mode==="priced"&&d.price!==null||mode==="drop"&&d.dropPercent!==null||mode==="rival"&&d.gapPercent!==null||mode==="opportunity"&&d.price!==null&&(d.dropPercent!==null||d.gapPercent!==null||d.manual))&&
 (d.title+" "+d.brand).toLocaleLowerCase("tr").includes(query.toLocaleLowerCase("tr")))
 .sort((a,b)=>sort==="price"?(a.price??a.recordedPrice??Infinity)-(b.price??b.recordedPrice??Infinity):sort==="recent"?Date.parse(b.detectedAt||"1970-01-01")-Date.parse(a.detectedAt||"1970-01-01"):Math.max(b.dropPercent??-1,b.gapPercent??-1)-Math.max(a.dropPercent??-1,a.gapPercent??-1)||a.id.localeCompare(b.id)),[deals,store,category,mode,query,sort]);
 const pages=Math.max(1,Math.ceil(shown.length/PAGE_SIZE)),currentPage=Math.min(page,pages),visible=shown.slice((currentPage-1)*PAGE_SIZE,currentPage*PAGE_SIZE);
 function chooseCategory(value:string){setCategory(value);setMode("all");setPage(1);}
 function clear(){setQuery("");setStore("all");setCategory("all");setMode("all");setPage(1);}
 function chooseMode(value:string){setMode(value);setPage(1);}
 function turn(value:number){setPage(value);document.getElementById("firsatlar")?.scrollIntoView({behavior:"smooth",block:"start"});}
 return <>
 <section className="discoveryHero"><div className="shell">
 <div className="discoveryHeading"><div><span className="eyebrow">İYİ FİYATIN PEŞİNDE</span><h1>Fırsatı gör. Fiyatı karşılaştır.</h1><p>Gerçek fiyat düşüşlerini keşfet, mağaza tekliflerini tek yerde incele.</p></div><div className="catalogueStat"><strong>{deals.length}</strong><span>ürün<br/>katalogda</span></div></div>
 <label className="catalogueSearch"><span aria-hidden="true">⌕</span><input aria-label="Ürünlerde ara" placeholder="Ne arıyorsun? Kulaklık, termos, makyaj…" value={query} onChange={e=>{setQuery(e.target.value);setMode("all");setPage(1);}}/><span className="searchHint">Ürün veya marka</span></label>
 <div className="featureShortcuts"><Link href="/brosurler"><CategoryIcon kind="book"/><span>İndirim Broşürleri<small>BİM · A101 · ŞOK · Migros</small></span><b aria-hidden="true">↗</b></Link><button onClick={()=>chooseMode("drop")}><CategoryIcon kind="spark"/><span>Fiyatı Düşenler<small>Önceki günlük kayda göre en az %15</small></span><b aria-hidden="true">↓</b></button><button onClick={clear}><CategoryIcon kind="grid"/><span>Tüm Ürünleri Keşfet<small>{deals.length} ürün · kategoriler ve mağazalar</small></span><b aria-hidden="true">↗</b></button></div>
 <div className="categoryHeading" id="kategoriler"><h2>Kategoriler</h2><button onClick={clear}>Tüm ürünleri göster ↗</button></div>
 <div className="categoryTiles" role="group" aria-label="Kategori seç"><button className={category==="all"?"active":""} aria-pressed={category==="all"} onClick={()=>chooseCategory("all")}><CategoryIcon kind="grid"/><b>Tüm kategoriler</b><small>{deals.length} ürün</small></button>{CATEGORIES.filter(c=>counts.has(c.id)).map(c=><button key={c.id} className={category===c.id?"active":""} aria-pressed={category===c.id} onClick={()=>chooseCategory(c.id)}><CategoryIcon kind={c.icon}/><b>{c.name}</b><small>{counts.get(c.id)} ürün</small></button>)}</div>
 </div></section>
 <section className="shell dealsSection" id="firsatlar">
 <div className="discoveryShortcuts modeTabs" role="group" aria-label="Ürün seçimi">{MODES.map(([id,label])=><button key={id} className={mode===id?"active":""} aria-pressed={mode===id} onClick={()=>chooseMode(id)}>{label} <small>{modeCount(id)}</small></button>)}</div>
 <div className="sectionHead"><div><span className="eyebrow">{category==="all"?"KEŞFET & KARŞILAŞTIR":CATEGORIES.find(c=>c.id===category)?.name}</span><h2>{MODES.find(([id])=>id===mode)?.[1]}<span className="count">{shown.length}</span></h2></div><p>{mode==="all"?"Tüm katalog burada; geçmiş fiyatlar tarihleriyle gösterilir.":"Fiyatlar son 6 saat içinde kontrol edildi. Son kontrol zamanı kartta."}</p></div>
 <div className="catalogueTools"><div className="storeFilters" role="group" aria-label="Mağazaya göre filtrele"><button className={store==="all"?"selected":""} aria-pressed={store==="all"} onClick={()=>{setStore("all");setPage(1);}}>Tüm mağazalar</button>{stores.map(([slug,name])=><button key={slug} className={store===slug?"selected":""} aria-pressed={store===slug} onClick={()=>{setStore(slug);setPage(1);}}>{name}</button>)}</div><label className="sortLabel"><span>Sırala</span><select aria-label="Fırsatları sırala" value={sort} onChange={e=>{setSort(e.target.value);setPage(1);}}><option value="advantage">En yüksek avantaj</option><option value="recent">Yeni keşfedilen</option><option value="price">En düşük fiyat</option></select></label></div>
 <p className="resultSummary" role="status">{shown.length?((currentPage-1)*PAGE_SIZE+1)+"–"+Math.min(currentPage*PAGE_SIZE,shown.length)+" / "+shown.length+" ürün":"Bu seçimde ürün bulunamadı."}</p>
 {visible.length?<div className="grid">{visible.map(deal=>{
 const current=deal.price!==null,displayPrice=deal.price??deal.recordedPrice,checkedAt=current?deal.checkedAt:deal.recordedCheckedAt;
 return <article className={"dealCard "+(!current?"recordedCard":"")} key={deal.id}>
 <Link className="productVisual" href={deal.detailHref} prefetch={false} aria-label={deal.title+" fiyatlarını incele"}><DealImage key={deal.imageUrl} src={deal.imageUrl} title={deal.title}/>{deal.dropPercent!==null?<span className="cardBadge dropBadge">%{deal.dropPercent.toFixed(0)} fiyat düştü</span>:deal.gapPercent!==null?<span className="cardBadge">Rakipten %{deal.gapPercent.toFixed(0)} ucuz</span>:<span className="cardBadge neutralBadge">{current?"Fiyat kontrol edildi":displayPrice!==null?"Son arama kaydı":"Ürün kataloğu"}</span>}</Link>
 <div className="cardBody"><div className={"merchant "+deal.merchantSlug}><span aria-hidden="true">●</span>{current?deal.merchant:deal.recordedPrice!==null?deal.recordedMerchant:deal.merchant}<span className="cardCategory">{deal.categoryName}</span></div>
 <h3><Link href={deal.detailHref} prefetch={false}>{deal.title}</Link></h3>
 <div className="cardPriceBlock">{deal.dropPercent!==null&&deal.oldPrice!==null?<div className="previousPrice"><s>{money.format(deal.oldPrice)}</s><span>Önceki günlük fiyat</span></div>:null}{!current&&displayPrice!==null?<span className="recordedPriceLabel">Son kaydedilen fiyat</span>:null}
 {displayPrice!==null?<div className="price">{money.format(displayPrice)}</div>:<div className="missingPrice">Henüz fiyat kaydı yok</div>}
 {deal.savings!==null?<p className="savings">{money.format(deal.savings)} fiyat farkı</p>:null}</div>
 <p className="rival">{deal.gapPercent!==null&&deal.competitorPrice!==null?<>{deal.competitorMerchant}: <b>{money.format(deal.competitorPrice)}</b><br/>Rakipten %{deal.gapPercent.toFixed(1)} daha ucuz</>:!current?"Bu kayıt güncel satın alma fiyatı değildir.":"Kargo ve kampanya koşullarını mağazada kontrol et."}</p>
 <Link className="dealCta" href={deal.detailHref} prefetch={false}>{deal.offerCount>1?deal.offerCount+" teklifi karşılaştır":"Fiyatı & geçmişi incele"} <span aria-hidden="true">↗</span></Link>
 {current?<a className="directStoreLink" href={deal.href} target="_blank" rel="nofollow sponsored noopener">{deal.merchant}’da satın al ↗</a>:null}
 {checkedAt?<div className="checked">{current?"Kontrol":"Arama kaydı"}: <time dateTime={checkedAt}>{time.format(new Date(checkedAt))}</time></div>:null}</div></article>;
 })}</div>:<div className="emptyState"><h3>{mode==="opportunity"?"Bu seçimde doğrulanmış fırsat yok.":"Bu seçimde ürün bulunamadı."}</h3><p>Kontrol edilen fiyatları veya tüm ürünleri inceleyebilirsin.</p><button onClick={clear}>Tüm ürünleri göster</button></div>}
 {pages>1?<nav className="pagination" aria-label="Ürün sayfaları"><button disabled={currentPage===1} onClick={()=>turn(currentPage-1)}>← Önceki</button><span>Sayfa {currentPage} / {pages}</span><button disabled={currentPage===pages} onClick={()=>turn(currentPage+1)}>Sonraki →</button></nav>:null}
 </section></>;
}
