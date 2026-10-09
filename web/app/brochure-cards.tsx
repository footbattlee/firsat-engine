import type {Brochure} from "../lib/brochure-parse";
import {BROCHURE_STORES} from "../lib/brochure-parse";
import {DealImage} from "./deal-image";
export function BrochureCards({brochures}:{brochures:Brochure[]}){
 const today=new Date().toLocaleDateString("en-CA",{timeZone:"Europe/Istanbul"});
 return <div className="brochureGrid">{BROCHURE_STORES.map(store=>{
 const row=brochures.find(b=>b.store===store.id),upcoming=row?.start&&row.start>today;
 return <article className="brochureCard" key={store.id}>
 <a href={row?.href||store.url} target="_blank" rel="noopener noreferrer" className="brochureCover" style={{"--store-color":store.color} as React.CSSProperties} aria-label={store.name+" broşürünü aç"}>
 {row?.image?<DealImage src={row.image} title={store.name+" "+row.dateLabel}/>:<div className="brochureGraphic"><strong>{store.name}</strong><span aria-hidden="true">▤</span><b>{row?.title||"İndirim broşürleri"}</b></div>}
 <span className="brochureTag">{upcoming?"Yakında":row?.end?"Tarihli katalog":"Resmi mağaza kaynağı"}</span></a>
 <div className="brochureBody"><h3>{store.name}</h3><p>{row?.dateLabel||store.description}</p><a href={row?.href||store.url} target="_blank" rel="noopener noreferrer">{row?"Broşürü incele":"Resmi broşürlere git"} <span aria-hidden="true">↗</span></a>{row?<small>{row.end?"Geçerlilik tarihleri mağaza kaynağından alınır.":"Aktüel başlangıç tarihi · stoklarla sınırlı."}</small>:<small>Güncel tarih ve broşür mağazanın sayfasında.</small>}</div></article>;
 })}</div>;
}
