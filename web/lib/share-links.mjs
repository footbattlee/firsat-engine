// Public identifiers only. The packed deal+offer pair keeps each published store link stable.
export const SHARE_ORIGIN="https://fırsatcı.com";
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const channels=new Set(["telegram","facebook","instagram","story","whatsapp","other"]);
export function shareChannel(value){return channels.has(String(value||"").toLowerCase())?String(value).toLowerCase():"other";}
export function encodeShareCode(deal,offer){
 if(!uuid.test(String(deal))||!uuid.test(String(offer)))throw Error("share link requires valid deal and offer UUIDs");
 const hex=(deal+offer).replaceAll("-","").toLowerCase();
 const bytes=hex.match(/.{2}/g).map(x=>String.fromCharCode(parseInt(x,16))).join("");
 return btoa(bytes).replaceAll("+","-").replaceAll("/","_").replaceAll("=","");
}
export function decodeShareCode(code){
 if(!/^[A-Za-z0-9_-]{43}$/.test(String(code)))return null;
 try{
  const bytes=atob(code.replaceAll("-","+").replaceAll("_","/")+"=");
  if(bytes.length!==32)return null;
  const hex=[...bytes].map(c=>c.charCodeAt(0).toString(16).padStart(2,"0")).join("");
  const id=x=>x.slice(0,8)+"-"+x.slice(8,12)+"-"+x.slice(12,16)+"-"+x.slice(16,20)+"-"+x.slice(20);
  const pair={deal:id(hex.slice(0,32)),offer:id(hex.slice(32))};
  return encodeShareCode(pair.deal,pair.offer)===code?pair:null;
 }catch{return null;}
}
export function brandedLink(data,channel){
 return SHARE_ORIGIN+"/f/"+encodeShareCode(String(data.id),String(data.offer_id||data.cheapest_offer_id))+"?s="+shareChannel(channel);
}
export function captionHasDeal(caption,id){
 const text=String(caption||"");
 // Keep reconciliation compatible with already-published legacy captions.
 if(new RegExp("[?&]deal="+String(id)+"(?:&|\\s|$)").test(text))return true;
 for(const raw of text.match(/https:\/\/[^\s<>"']+/g)||[]){
  try{
   const url=new URL(raw);
   if(url.hostname!=="xn--frsatc-p9af.com"||url.protocol!=="https:"||url.username||url.password||url.port)continue;
   const m=url.pathname.match(/^\/f\/([A-Za-z0-9_-]{43})$/);
   if(m&&decodeShareCode(m[1])?.deal===String(id).toLowerCase())return true;
  }catch{/* Not a valid product share link. */}
 }
 return false;
}
