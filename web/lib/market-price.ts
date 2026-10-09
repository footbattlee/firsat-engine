import {activeCatalogueEligible,type Snapshot} from "./policy.ts";
export const PURCHASE_CHECK_AGE_MS=6*60*60*1000;
export const RECORDED_PRICE_AGE_MS=7*24*60*60*1000;
export function recent(raw:unknown,age:number,now=Date.now()){
 const value=Date.parse(String(raw||""));return Number.isFinite(value)&&value<=now+5000&&now-value<age;
}
export function priceFacts(row:Snapshot,now=Date.now()){
 const active=activeCatalogueEligible(row,now),price=Number(row.price);
 const current=active&&row.status!=="ended"&&price>0&&Number.isFinite(price)&&recent(row.price_checked_at,PURCHASE_CHECK_AGE_MS,now);
 const rival=Number(row.competitor_price),old=Number(row.old_price);
 const rivalValid=current&&rival>0&&Number.isFinite(rival)&&recent(row.competitor_checked_at,PURCHASE_CHECK_AGE_MS,now);
 const reference=Date.parse(String(row.old_checked_at||"")),checked=Date.parse(String(row.price_checked_at||""));
 const previousDay=Number.isFinite(reference)&&Number.isFinite(checked)&&new Date(reference).toLocaleDateString("en-CA",{timeZone:"Europe/Istanbul"})!==new Date(checked).toLocaleDateString("en-CA",{timeZone:"Europe/Istanbul"});
 const oldValid=current&&old>0&&Number.isFinite(old)&&previousDay&&reference<checked&&checked-reference<=RECORDED_PRICE_AGE_MS;
 const ratio=(reference:number)=>(reference-price)/reference*100;
 const gap=rivalValid?ratio(rival):null,drop=oldValid?ratio(old):null;
 const recorded=Number(row.recorded_price);
 return {price:current?price:null,checkedAt:current?String(row.price_checked_at):null,
 competitorPrice:rivalValid?rival:null,gapPercent:gap!==null&&gap>=15&&gap<70?Math.round(gap*100)/100:null,
 oldPrice:oldValid?old:null,oldCheckedAt:oldValid?String(row.old_checked_at):null,
 dropPercent:drop!==null&&drop>=15&&drop<70?Math.round(drop*100)/100:null,
 savings:oldValid&&drop!==null&&drop>=15&&drop<70?Math.round((old-price)*100)/100:null,
 recordedPrice:active&&recorded>0&&Number.isFinite(recorded)&&recent(row.recorded_checked_at,RECORDED_PRICE_AGE_MS,now)?recorded:null,
 recordedCheckedAt:row.recorded_checked_at?String(row.recorded_checked_at):null,
 };
}
