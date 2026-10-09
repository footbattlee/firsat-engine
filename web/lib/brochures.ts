import "server-only";
import {parseHTML} from "linkedom";
import {BROCHURE_STORES,brochureDate,safeBrochureUrl,type Brochure} from "./brochure-parse";
export {BROCHURE_STORES} from "./brochure-parse";
async function source(url:string){
 const r=await fetch(url,{headers:{"User-Agent":"Mozilla/5.0","Accept-Language":"tr-TR"},next:{revalidate:3600},signal:AbortSignal.timeout(7000)});
 if(!r.ok)throw Error("source unavailable");const html=await r.text();if(html.length>2500000)throw Error("source too large");return parseHTML(html).document;
}
async function storeBrochures(store:typeof BROCHURE_STORES[number]):Promise<Brochure[]>{
 const doc=await source(store.url),rows:Brochure[]=[];
 if(store.id==="bim"){
  const links=[...doc.querySelectorAll('a[href*="Bim_AfisKey"]')],seen=new Set<string>();
  for(const a of links){const title=a.textContent?.trim()||"",href=safeBrochureUrl(a.getAttribute("href")||"",store.url),date=brochureDate(title);if(!href||!date||seen.has(href))continue;seen.add(href);rows.push({store:store.id,name:store.name,title:"Aktüel ürünler",dateLabel:title,href,...date,image:null,color:store.color,sourceUrl:store.url});}
  const today=new Date().toLocaleDateString("en-CA",{timeZone:"Europe/Istanbul"});
  const past=rows.filter(r=>r.start!<=today).sort((a,b)=>b.start!.localeCompare(a.start!)).slice(0,1);
  const future=rows.filter(r=>r.start!>today).sort((a,b)=>a.start!.localeCompare(b.start!)).slice(0,1);
  return Promise.all([...past,...future].map(async row=>{try{const detail=await source(row.href);const image=[...detail.querySelectorAll('a[href*="/uploads/afisler/"] img[src]')].map(i=>i.getAttribute("src")||"").find(src=>src.includes("/uploads/afisler/"));return {...row,image:image?safeBrochureUrl(image,row.href):null};}catch{return row;}}));
 }
 if(store.id==="migros"){
  const button=doc.querySelector("button[mcdate][source]"),title=button?.getAttribute("mcdate")||"",date=brochureDate(title),href=safeBrochureUrl(button?.getAttribute("source")||"",store.url);
  if(button&&date&&href){const box=button.parentElement?.parentElement;const src=box?.querySelector("img")?.getAttribute("src");rows.push({store:store.id,name:store.name,title:"Migroskop",dateLabel:title,href,...date,image:src?safeBrochureUrl(src,store.url):null,color:store.color,sourceUrl:store.url});}
 }
 if(store.id==="sok"){
  for(const a of doc.querySelectorAll('a[href*=".pdf"]')){const title=a.textContent?.replace(/İndir|⬇/g,"").replace(/Haftanın\s*Fırsatları/g,"Haftanın Fırsatları ").replace(/Hafta Sonu\s*Fırsatları/g,"Hafta Sonu Fırsatları ").replace(/\s+/g," ").trim()||"",date=brochureDate(title),href=safeBrochureUrl(a.getAttribute("href")||"",store.url);if(date&&href)rows.push({store:store.id,name:store.name,title:"Haftanın fırsatları",dateLabel:title,href,...date,image:null,color:store.color,sourceUrl:store.url});}
 }
 return rows;
}
export async function getBrochures(){
 const results=await Promise.allSettled(BROCHURE_STORES.map(storeBrochures));
 return results.flatMap(r=>r.status==="fulfilled"?r.value:[]).slice(0,12);
}
