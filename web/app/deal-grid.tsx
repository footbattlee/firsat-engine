"use client";
import { useEffect,useMemo,useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { Deal } from "../lib/deals";
import { CATEGORIES } from "../lib/categories";
import { DealImage } from "./deal-image";
import { CategoryIcon } from "./category-icon";
const money=new Intl.NumberFormat("tr-TR",{style:"currency",currency:"TRY"});
const time=new Intl.DateTimeFormat("tr-TR",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",timeZone:"Europe/Istanbul"});
const PAGE_SIZE=24;
function stringValue(v:unknown){return typeof v==="string"?v:"";}
export function DealGrid({deals,initial={}}:{deals:Deal[];initial?:Record<string,unknown>}) {
 const [query,setQuery]=useState(stringValue(initial.q)),[store,setStore]=useState(stringValue(initial.magaza)||"all");
 const [category,setCategory]=useState(stringValue(initial.kategori)||"all"),[sort,setSort]=useState(stringValue(initial.sirala)||"recent");
 const [mode,setMode]=useState(stringValue(initial.secim)||"all");
 const [page,setPage]=useState(Math.max(1,Number.parseInt(stringValue(initial.sayfa),10)||1));
 const router=useRouter();
 useEffect(()=>{
  const refresh=()=>{if(document.visibilityState==="visible")router.refresh();};
  const timer=window.setInterval(refresh,60000);document.addEventListener("visibilitychange",refresh);
  return()=>{window.clearInterval(timer);document.removeEventListener("visibilitychange",refresh);};
 },[router]);
 useEffect(()=>{
  const params=new URLSearchParams();
  if(query)params.set("q",query);if(store!=="all")params.set("magaza",store);
  if(category!=="all")params.set("kategori",category);if(sort!=="recent")params.set("sirala",sort);
  if(mode!=="all")params.set("secim",mode);if(page>1)params.set("sayfa",String(page));
  const url="/"+(params.size?"?"+params:"")+window.location.hash;
  window.history.replaceState(null,"",url);
 },[query,store,category,sort,mode,page]);
 const stores=useMemo(()=>[...new Map(deals.map(d=>[d.merchantSlug,d.merchant])).entries()],[deals]);
 const counts=useMemo(()=>{const m=new Map<string,number>();for(const d of deals)m.set(d.category,(m.get(d.category)||0)+1);return m;},[deals]);
 const shown=useMemo(()=>deals.filter(d=>(store==="all"||d.merchantSlug===store)&&(category==="all"||d.category===category)&&
  (mode!=="verified"||d.gapPercent!==null)&&(d.title+" "+d.brand).toLocaleLowerCase("tr").includes(query.toLocaleLowerCase("tr")))
  .sort((a,b)=>sort==="price"?(a.price??Infinity)-(b.price??Infinity):sort==="gap"?(b.gapPercent??-1)-(a.gapPercent??-1):
  Date.parse(b.detectedAt||"1970-01-01")-Date.parse(a.detectedAt||"1970-01-01")||a.id.localeCompare(b.id)),[deals,store,category,mode,query,sort]);
 const pages=Math.max(1,Math.ceil(shown.length/PAGE_SIZE)),currentPage=Math.min(page,pages);
 const visible=shown.slice((currentPage-1)*PAGE_SIZE,currentPage*PAGE_SIZE);
 function chooseCategory(value:string){setCategory(value);setPage(1);}
 function clear(){setQuery("");setStore("all");setCategory("all");setMode("all");setPage(1);}
 function turn(value:number){setPage(value);document.getElementById("firsatlar")?.scrollIntoView({behavior:"smooth",block:"start"});}
 return <>
 <section className="discoveryHero"><div className="shell">
 <div className="discoveryHeading"><div><span className="eyebrow">FIRSATI SEN SEÇ</span><h1>Ne arıyorsun?</h1><p>Mağazaları karşılaştır. Fiyat geçmişine bak. İyi fiyatı yakala.</p></div>
 <div className="catalogueStat"><strong>{deals.length}</strong><span>aktif ürün<br/>tek yerde</span></div></div>
 <label className="catalogueSearch"><span aria-hidden="true">⌕</span><input aria-label="Ürünlerde ara" placeholder="Kulaklık, termos, vitamin…" value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}}/><span className="searchHint">Ürün veya marka</span></label>
 <div className="categoryHeading" id="kategoriler"><h2>Kategoriler</h2><button onClick={clear}>Tüm ürünleri göster ↗</button></div>
 <div className="categoryTiles" role="group" aria-label="Kategori seç">
 <button className={category==="all"?"active":""} aria-pressed={category==="all"} onClick={()=>chooseCategory("all")}><CategoryIcon kind="grid"/><b>Tüm kategoriler</b><small>{deals.length} ürün</small></button>
 {CATEGORIES.filter(c=>counts.has(c.id)).map(c=><button key={c.id} className={category===c.id?"active":""} aria-pressed={category===c.id} onClick={()=>chooseCategory(c.id)}><CategoryIcon kind={c.icon}/><b>{c.name}</b><small>{counts.get(c.id)} ürün</small></button>)}
 </div>
 <div className="discoveryShortcuts"><button aria-pressed={mode==="all"} className={mode==="all"?"active":""} onClick={()=>{setMode("all");setPage(1);}}>≋ Tüm fırsatlar</button><button aria-pressed={mode==="verified"} className={mode==="verified"?"active":""} onClick={()=>{setMode("verified");setPage(1);}}>✓ Fiyat avantajı doğrulananlar</button><span>Günlük arama kayıtlarıyla fiyat geçmişi</span></div>
 </div></section>
 <section className="shell dealsSection" id="firsatlar">
 <div className="sectionHead"><div><span className="eyebrow">KEŞFET & KARŞILAŞTIR</span><h2>{category==="all"?"Tüm fırsatlar":CATEGORIES.find(c=>c.id===category)?.name||"Fırsatlar"}<span className="count">{shown.length}</span></h2></div><p>Güncel fiyatı doğrulanmayan üründe rakam gösterilmez.</p></div>
 <div className="catalogueTools"><div className="storeFilters" role="group" aria-label="Mağazaya göre filtrele"><button className={store==="all"?"selected":""} aria-pressed={store==="all"} onClick={()=>{setStore("all");setPage(1);}}>Tüm mağazalar</button>{stores.map(([slug,name])=><button key={slug} className={store===slug?"selected":""} aria-pressed={store===slug} onClick={()=>{setStore(slug);setPage(1);}}>{name}</button>)}</div>
 <label className="sortLabel"><span>Sırala</span><select aria-label="Fırsatları sırala" value={sort} onChange={e=>{setSort(e.target.value);setPage(1);}}><option value="recent">Yeni keşfedilen</option><option value="gap">En yüksek fiyat avantajı</option><option value="price">En düşük güncel fiyat</option></select></label></div>
 <p className="resultSummary" role="status">{shown.length?((currentPage-1)*PAGE_SIZE+1)+"–"+Math.min(currentPage*PAGE_SIZE,shown.length)+" / "+shown.length+" ürün":"Bu seçimde ürün bulunamadı."}</p>
 {visible.length?<div className="grid">{visible.map(deal=><article className="dealCard" key={deal.id}>
 <Link className="productVisual" href={deal.detailHref} prefetch={false} aria-label={deal.title+" fiyatlarını incele"}><DealImage key={deal.imageUrl} src={deal.imageUrl} title={deal.title}/><span className="cardBadge">{deal.gapPercent!==null?"Rakipten %"+deal.gapPercent.toFixed(0)+" ucuz":deal.price!==null?"Fiyat kontrol edildi":"Fiyat mağazada"}</span></Link>
 <div className="cardBody"><div className={"merchant "+deal.merchantSlug}><span aria-hidden="true">●</span>{deal.merchant}<span className="cardCategory">{deal.categoryName}</span></div>
 <h3><Link href={deal.detailHref} prefetch={false}>{deal.title}</Link></h3>
 {deal.price!==null?<div className="price">{money.format(deal.price)}</div>:<div className="storePrice">Fiyatı mağazada gör</div>}
 <p className="rival">{deal.competitorPrice!==null?<>{deal.competitorMerchant}: <b>{money.format(deal.competitorPrice)}</b></>:deal.price!==null?"Güncel mağaza fiyatı; karşılaştırma doğrulanmadı.":"Güncel fiyatı henüz doğrulayamadık."}</p>
 <Link className="dealCta" href={deal.detailHref} prefetch={false}>Fiyatları & geçmişi incele <span aria-hidden="true">↗</span></Link>
 <a className="directStoreLink" href={deal.href} target="_blank" rel="nofollow sponsored noopener">{deal.merchant}’da gör ↗</a>
 <div className="checked">{deal.checkedAt?<><span aria-hidden="true">✓</span> Kontrol: <time dateTime={deal.checkedAt}>{time.format(new Date(deal.checkedAt))}</time></>:"Son fiyat ve stok mağazada."}</div></div></article>)}</div>:
 <div className="emptyState"><h3>Bu seçimde ürün bulunamadı.</h3><p>Başka bir ürün adı, kategori veya mağaza deneyebilirsin.</p><button onClick={clear}>Tüm ürünleri göster</button></div>}
 {pages>1?<nav className="pagination" aria-label="Ürün sayfaları"><button disabled={currentPage===1} onClick={()=>turn(currentPage-1)}>← Önceki</button><span>Sayfa {currentPage} / {pages}</span><button disabled={currentPage===pages} onClick={()=>turn(currentPage+1)}>Sonraki →</button></nav>:null}
 </section></>;
}
