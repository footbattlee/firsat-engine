import "server-only";
import { cache } from "react";
import { eligible, currentPriceEligible, safeImage, safeDestination, validListingId, type Snapshot } from "./policy";
import { categoryFor, CATEGORIES } from "./categories";
const SUPABASE_URL = (process.env.SUPABASE_URL || "https://cmexmobjpeavlppmffqi.supabase.co").replace(/\/$/, "");
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
export type Deal = {
 id:string; title:string; brand:string; price:number|null; competitorPrice:number|null; gapPercent:number|null;
 merchant:string; merchantSlug:string; competitorMerchant:string; imageUrl:string|null; href:string;
 detailHref:string; checkedAt:string|null; detectedAt:string|null; manual:boolean; affiliate:boolean;
 category:string; categoryName:string;
};
export type StoreOffer={id:string;merchant_name:string;merchant_slug:string;seller:string|null;price:number|null;
 in_stock:boolean|null;checked_at:string|null;product_url:string;affiliate_url:string|null};
export type HistoryPoint={offer_id:string;merchant:string;day:string;price:number;checked_at:string};
export async function rpc<T>(name:string,args:Record<string,unknown>):Promise<T[]> {
 if(!SERVICE_KEY)throw new Error("Website data connection unavailable");
 const r=await fetch(SUPABASE_URL+"/rest/v1/rpc/"+name,{method:"POST",
  headers:{apikey:SERVICE_KEY,Authorization:"Bearer "+SERVICE_KEY,"Content-Type":"application/json"},
  body:JSON.stringify(args),cache:"no-store",signal:AbortSignal.timeout(10000)});
 if(!r.ok)throw new Error("Website data unavailable");
 return r.json();
}
export async function snapshots(query:string):Promise<Snapshot[]> {
 if(!SERVICE_KEY)throw new Error("Website data connection unavailable");
 const r=await fetch(SUPABASE_URL+"/rest/v1/homepage_deals?"+query,{
 headers:{apikey:SERVICE_KEY,Authorization:"Bearer "+SERVICE_KEY},cache:"no-store",signal:AbortSignal.timeout(10000)});
 if(!r.ok)throw new Error("Website data unavailable");
 return r.json();
}
export const getSnapshot=cache(async(id:string):Promise<Snapshot|null>=>{
 if(!validListingId(id))return null;
 const rows=await rpc<Snapshot>("website_catalogue",{p_listing_id:id});return rows[0]||null;
});
export function toDeal(row:Snapshot):Deal {
 const fresh=eligible(row),current=currentPriceEligible(row),price=fresh||current?Number(row.price):null;
 const rival=fresh&&!row.manual_id?Number(row.competitor_price):null;
 const category=categoryFor(String(row.title),String(row.category_name||""));
 return {id:String(row.id),title:String(row.title),brand:String(row.brand||""),price,
 competitorPrice:rival,gapPercent:price!==null&&rival?Math.round((rival-price)/rival*10000)/100:null,
 merchant:String(row.merchant_name),merchantSlug:String(row.merchant_slug),
 competitorMerchant:fresh?String(row.competitor_name||""):"",imageUrl:safeImage(row.image_url),
 href:"/urun/"+encodeURIComponent(String(row.id)),detailHref:"/urun-detay/"+encodeURIComponent(String(row.id)),
 checkedAt:fresh?String(row.checked_at):current?String(row.price_checked_at):null,
 detectedAt:row.detected_at?String(row.detected_at):null,
 manual:Boolean(row.manual_id),affiliate:Boolean(row.affiliate_url),category,
 categoryName:CATEGORIES.find(c=>c.id===category)?.name||"Diğer"};
}
export async function getDeals():Promise<Deal[]> {
 // Fetch every active listing in stable pages; PostgREST's row cap is not a catalogue cap.
 const all:Snapshot[]=[];
 for(let offset=0;;offset+=500){
  if(!SERVICE_KEY)throw new Error("Website data connection unavailable");
  const r=await fetch(SUPABASE_URL+"/rest/v1/rpc/website_catalogue?offset="+offset+"&limit=500",{
   method:"POST",headers:{apikey:SERVICE_KEY,Authorization:"Bearer "+SERVICE_KEY,"Content-Type":"application/json"},
   body:"{}",cache:"no-store",signal:AbortSignal.timeout(10000)});
  if(!r.ok)throw new Error("Website data unavailable");
  const page:Snapshot[]=await r.json();all.push(...page);if(page.length<500)break;
 }
 return [...new Map(all.map(row=>[String(row.id),row])).values()].filter(row=>safeDestination(row.affiliate_url||row.product_url,row.merchant_slug)&&String(row.title||"").trim()).map(toDeal);
}
export async function getProductData(id:string) {
 const [row,offers,history]=await Promise.all([getSnapshot(id),
  rpc<StoreOffer>("website_product_offers",{p_listing_id:id}),rpc<HistoryPoint>("website_price_history",{p_listing_id:id})]);
 return {row,offers:offers.filter(o=>safeDestination(o.affiliate_url||o.product_url,o.merchant_slug)),history};
}
