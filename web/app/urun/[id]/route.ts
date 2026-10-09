import { getSnapshot } from "../../../lib/deals";
import { eligible, currentPriceEligible, catalogueEligible, activeCatalogueEligible, safeDestination } from "../../../lib/policy";
import { recordTraffic } from "../../../lib/traffic";
export const dynamic="force-dynamic";
export const runtime="nodejs";
// Product discovery links display no price or discount promise.
export async function GET(req:Request,context:{params:Promise<{id:string}>}){
 const {id}=await context.params;
 try{
  const row=await getSnapshot(id);
  if(!row||(!eligible(row)&&!currentPriceEligible(row)&&!catalogueEligible(row)&&!activeCatalogueEligible(row)))return new Response('Bu ürün bağlantısı artık listede değil. Güncel ürünler için ana sayfaya dön.',{status:410,headers:{"Cache-Control":"no-store"}});
  const target=safeDestination(row.affiliate_url||row.product_url,row.merchant_slug);
  if(!target)return new Response("Bağlantı kullanılamıyor",{status:404});
  await recordTraffic(req,"outbound","/urun/"+id,id,String(row.merchant_name));
  return new Response(null,{status:302,headers:{Location:target,"Cache-Control":"no-store","Referrer-Policy":"no-referrer","X-Robots-Tag":"noindex"}});
 }catch{return new Response("Mağaza bağlantısı şu anda kullanılamıyor",{status:503,headers:{"Cache-Control":"no-store"}});}
}
export const HEAD=GET;
