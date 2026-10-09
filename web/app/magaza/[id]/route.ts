import {getSnapshot,rpc,type StoreOffer} from "../../../lib/deals";
import {validListingId,safeDestination} from "../../../lib/policy";
import {recordTraffic} from "../../../lib/traffic";
export const dynamic="force-dynamic";export const runtime="nodejs";
export async function GET(req:Request,context:{params:Promise<{id:string}>}){
 const {id}=await context.params,offer=new URL(req.url).searchParams.get("offer")||"";
 if(!validListingId(id)||!validListingId(offer)||offer.startsWith("manual-"))return new Response("Bağlantı bulunamadı",{status:404});
 try{
  if(!await getSnapshot(id))return new Response("Ürün artık aktif değil",{status:410});
  const offers=await rpc<StoreOffer>("website_product_offers",{p_listing_id:id});
  const matched=offers.find(o=>o.id===offer);
  const target=matched?safeDestination(matched.affiliate_url||matched.product_url,matched.merchant_slug):null;
  if(!target)return new Response("Mağaza teklifi bulunamadı",{status:404});
  await recordTraffic(req,"outbound","/magaza/"+id+"/"+offer,id,matched!.merchant_name);
  return new Response(null,{status:302,headers:{Location:target,"Cache-Control":"no-store","Referrer-Policy":"no-referrer","X-Robots-Tag":"noindex"}});
 }catch{return new Response("Mağaza bağlantısı şu anda kullanılamıyor",{status:503});}
}
export const HEAD=GET;
