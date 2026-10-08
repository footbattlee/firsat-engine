import {brandedLink,captionHasDeal} from "../_shared/share-links.mjs";
import {discountPresentation} from './core.ts';
export const channels=['story','telegram','facebook'] as const;
export function caption(d:any,base:string,channel:string){
 const discount=discountPresentation(d);
 const money=(v:number)=>new Intl.NumberFormat('tr-TR',{maximumFractionDigits:2}).format(v)+' TL';
 const percent=new Intl.NumberFormat('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:2}).format(discount.percent);
 const link=brandedLink(d,channel);
 return `🔥 FİYATZADE FIRSATI\n\n${String(d.title).slice(0,300)}\n\n🛒 ${d.merchant}\n💸 ${discount.repeat?'Önceki paylaşım fiyatı':'Rakip fiyat'}: ${money(discount.comparisonPrice)}\n🔥 Fırsat fiyatı: ${money(d.cheapest_price)}\n📉 ${discount.repeat?'Son paylaşımdan sonra %'+percent+' düştü':'Rakipten %'+percent+' daha ucuz'}\n\n🔗 Fırsata git: ${link}\n\nFiyat bilgisi son taramaya aittir; fiyat ve stok değişebilir.\n#işbirliği #reklam #indirim #fırsat`;
}
export class DeliveryError extends Error{
 code:string;retryable:boolean;ambiguous:boolean;retryAfter:number;
 constructor(code:string,retryable=false,ambiguous=false,retryAfter=300){super(code);this.code=code;this.retryable=retryable;this.ambiguous=ambiguous;this.retryAfter=retryAfter;}
}
// Preserve useful API error codes without logging tokens, request URLs or bodies.
export async function apiJSON(fetcher:typeof fetch,url:string,init:RequestInit={},timeout=45000){
 let r:Response;
 try{r=await fetcher(url,{...init,signal:AbortSignal.timeout(timeout)});}
 catch{throw new DeliveryError('network-outcome-unknown',false,true);}
 let j:any;try{j=await r.json();}catch{throw new DeliveryError('response-outcome-unknown',false,true);}
 if(!r.ok||j.ok===false||j.error){
  const code=Number(j.error?.code||j.error_code||r.status);
  const retry=code===429||[1,2,4,17,32,613].includes(code)||r.status>=500;
  throw new DeliveryError('api-rejected:'+code,retry,false,Number(j.parameters?.retry_after)||300);
 }
 return j;
}
export function matchingMedia(rows:any[],id:string,slot:string){
 const when=Date.parse(slot);if(!Number.isFinite(when))return [];
 // Exact tracking parameter and publication window avoid matching an older deal.
 return rows.filter(m=>m.media_type==='IMAGE'&&
  captionHasDeal(m.caption,id)&&
  Date.parse(m.timestamp)>=when-5000&&Date.parse(m.timestamp)<=when+600000);
}
export async function deliverChannels(q:any,deps:any){
 const settled=await Promise.allSettled(channels.map(async platform=>{
  const claim=await deps.claim(q.candidate_id,platform);
  if(!claim)return null;
  try{
   const id=await deps.send(platform,q.snapshot);
   const saved=await deps.finish(q.candidate_id,platform,claim,{status:'published',external_post_id:id,published_at:new Date().toISOString(),error_message:null});
   if(saved===false)throw new DeliveryError('delivery-record-not-confirmed',false,true);
   return {platform,status:'published'};
  }catch(error){
   const e=error instanceof DeliveryError?error:new DeliveryError('delivery-outcome-unknown',false,true);
   await deps.finish(q.candidate_id,platform,claim,{
    status:'failed',error_message:e.code,
    next_attempt_at:e.retryable&&!e.ambiguous?new Date(Date.now()+Math.max(60,e.retryAfter)*1000).toISOString():'infinity'
   });
   return {platform,status:'failed',reason:e.code};
  }
 }));
 return settled.flatMap((r,i)=>r.status==='fulfilled'?(r.value?[r.value]:[]):[{platform:channels[i],status:'pending',reason:'delivery-record-recovery-scheduled'}]);
}
