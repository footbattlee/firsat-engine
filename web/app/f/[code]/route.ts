import { decodeShareCode, shareChannel } from "../../../lib/share-links.mjs";
export const dynamic="force-dynamic";
export const runtime="nodejs";
const CLICK_BASE="https://cmexmobjpeavlppmffqi.supabase.co/functions/v1/deal-click";
export async function GET(req:Request,context:{params:Promise<{code:string}>}){
 const {code}=await context.params;
 const pair=decodeShareCode(code);
 const headers={"Cache-Control":"no-store","X-Robots-Tag":"noindex, nofollow","Referrer-Policy":"strict-origin-when-cross-origin"};
 if(!pair)return new Response("Ürün bağlantısı bulunamadı.",{status:404,headers});
 const channel=shareChannel(new URL(req.url).searchParams.get("s"));
 const target=CLICK_BASE+"?"+new URLSearchParams({...pair,channel});
 // Browser follows the tracking redirect: its real IP, UA and navigation/prefetch
 // evidence reach the existing click classifier. A server-side proxy would hide these.
 return new Response(null,{status:302,headers:{...headers,Location:target}});
}
export const HEAD=GET;
