import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const env=(n:string)=>Deno.env.get(n)?.trim()||"";
const BOT=env("TELEGRAM_BOT_TOKEN");
const TG_API=`https://api.telegram.org/bot${BOT}`;
const PUBLISH_CHAT_ID=env("TELEGRAM_PUBLISH_CHAT_ID");
const IG_TOKEN=env("INSTAGRAM_ACCESS_TOKEN");
const IG_USER=env("INSTAGRAM_USER_ID");
const IG_BASE=env("INSTAGRAM_GRAPH_BASE")||"https://graph.instagram.com";
const FB_TOKEN=env("FACEBOOK_SYSTEM_USER_TOKEN");
const FB_PAGE=env("FACEBOOK_PAGE_ID");
const FB_VER=env("FACEBOOK_GRAPH_VERSION")||"v26.0";
const WEBHOOK_SECRET=env("TELEGRAM_WEBHOOK_SECRET");
const BUCKET=env("INSTAGRAM_MEDIA_BUCKET")||"instagram-media";
const sbUrl=env("SUPABASE_URL");
const service=env("SUPABASE_SERVICE_ROLE_KEY") || (()=>{try{return JSON.parse(env("SUPABASE_SECRET_KEYS")).default||""}catch{return ""}})();
const sb=createClient(sbUrl,service);

async function tg(method:string, body:any) {
  const r=await fetch(`${TG_API}/${method}`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
  const j=await r.json(); if(!j.ok) throw new Error(`Telegram ${method}: ${JSON.stringify(j)}`); return j.result;
}
async function ack(id:string,text:string){try{await tg("answerCallbackQuery",{callback_query_id:id,text})}catch(e){console.error("ack",e)}}
const money=(v:any)=>new Intl.NumberFormat("tr-TR",{style:"currency",currency:"TRY",minimumFractionDigits:0,maximumFractionDigits:2}).format(Number(v));
function pubCaption(d:any,html=false){
 const gap=Number(d.gap_percent).toFixed(2).replace(".",",");
 const title=String(d.title), merchant=String(d.merchant);
 return `🔥 FİYATZADE FIRSATI\n\n${html?"<b>":""}${title}${html?"</b>":""}\n\n🛒 ${merchant}\n💸 Rakip fiyat: ${money(d.competitor_price)}\n🔥 Fırsat fiyatı: ${money(d.cheapest_price)}\n📉 %${gap} daha ucuz\n\n${html?`🔗 <a href="${d.product_url}">Fırsata Git</a>\n\n`:`🔗 Fırsata git: ${d.product_url}\n\n`}Fiyatlar değişebilir. Satın almadan önce mağaza fiyatını kontrol edin.\n\n#işbirliği #reklam #fiyatzade #indirim #fırsat`;
}
async function candidate(id:string){
 const {data,error}=await sb.from("deal_candidates").select("id,canonical_product_id,cheapest_offer_id,cheapest_merchant_id,gap_percent,cheapest_price,competitor_price").eq("id",id).single();
 if(error) throw error;
 const [{data:cp,error:cpErr},{data:offer,error:offerErr},{data:merchant,error:merchantErr}]=await Promise.all([
   sb.from("canonical_products").select("title").eq("id",data.canonical_product_id).single(),
   sb.from("offers").select("product_url").eq("id",data.cheapest_offer_id).single(),
   sb.from("merchants").select("name").eq("id",data.cheapest_merchant_id).single()
 ]);
 if(cpErr) throw cpErr;if(offerErr) throw offerErr;if(merchantErr) throw merchantErr;
 return {id,title:cp?.title||"-",merchant:merchant?.name||"-",gap_percent:data.gap_percent,cheapest_price:data.cheapest_price,competitor_price:data.competitor_price,product_url:offer?.product_url||""};
}
async function ensureRows(id:string){
 for(const platform of ["telegram","instagram","facebook"]){
  const {data}=await sb.from("deal_publications").select("status").eq("deal_candidate_id",id).eq("platform",platform).maybeSingle();
  if(!data) await sb.from("deal_publications").insert({deal_candidate_id:id,platform,status:"pending",updated_at:new Date().toISOString()});
 }
}
async function state(id:string,p:string){const {data}=await sb.from("deal_publications").select("*").eq("deal_candidate_id",id).eq("platform",p).maybeSingle();return data}
async function mark(id:string,p:string,status:string,external_post_id?:string,error_message?:string){
 const x:any={status,updated_at:new Date().toISOString(),error_message:error_message||null};
 if(external_post_id)x.external_post_id=external_post_id;if(status==="published")x.published_at=new Date().toISOString();
 await sb.from("deal_publications").update(x).eq("deal_candidate_id",id).eq("platform",p);
}
async function adminPhotoBytes(msg:any){
 const photos=msg?.photo||[]; if(!photos.length) throw new Error("Admin mesajinda preview photo yok");
 const file=await tg("getFile",{file_id:photos[photos.length-1].file_id});
 const r=await fetch(`https://api.telegram.org/file/bot${BOT}/${file.file_path}`); if(!r.ok)throw new Error("Telegram photo download failed"); return new Uint8Array(await r.arrayBuffer());
}
async function publishTelegram(d:any,bytes:Uint8Array){
 const fd=new FormData();fd.set("chat_id",PUBLISH_CHAT_ID);fd.set("caption",pubCaption(d,true));fd.set("parse_mode","HTML");fd.set("photo",new Blob([bytes],{type:"image/jpeg"}),"fiyatzade.jpg");
 const r=await fetch(`${TG_API}/sendPhoto`,{method:"POST",body:fd});const j=await r.json();if(!j.ok)throw new Error(JSON.stringify(j));return String(j.result.message_id);
}
async function uploadImage(id:string,bytes:Uint8Array){
 const path=`deals/${id}/webhook-instagram.jpg`;const {error}=await sb.storage.from(BUCKET).upload(path,bytes,{contentType:"image/jpeg",upsert:true});if(error)throw error;
 return sb.storage.from(BUCKET).getPublicUrl(path).data.publicUrl;
}
async function publishInstagram(d:any,bytes:Uint8Array){
 const imageUrl=await uploadImage(d.id,bytes);
 let r=await fetch(`${IG_BASE}/${IG_USER}/media`,{method:"POST",headers:{Authorization:`Bearer ${IG_TOKEN}`,"content-type":"application/x-www-form-urlencoded"},body:new URLSearchParams({image_url:imageUrl,caption:pubCaption(d,false)})});
 let j=await r.json();if(!r.ok||!j.id)throw new Error(`IG container ${JSON.stringify(j)}`);
 const creationId=String(j.id);
 let last:any=null;
 for(let i=0;i<12;i++){
   await new Promise(resolve=>setTimeout(resolve,5000));
   const sr=await fetch(`${IG_BASE}/${creationId}?fields=status_code,status&access_token=${encodeURIComponent(IG_TOKEN)}`);
   const sj=await sr.json(); last=sj;
   if(sj.status_code==="FINISHED") break;
   if(["ERROR","EXPIRED"].includes(String(sj.status_code))) throw new Error(`IG container status ${JSON.stringify(sj)}`);
 }
 if(last?.status_code!=="FINISHED") throw new Error(`IG container not ready ${JSON.stringify(last)}`);
 r=await fetch(`${IG_BASE}/${IG_USER}/media_publish`,{method:"POST",headers:{Authorization:`Bearer ${IG_TOKEN}`,"content-type":"application/x-www-form-urlencoded"},body:new URLSearchParams({creation_id:creationId})});
 j=await r.json();if(!r.ok||!j.id)throw new Error(`IG publish ${JSON.stringify(j)}`);return String(j.id);
}
async function facebookPageToken(){
 const r=await fetch(`https://graph.facebook.com/${FB_VER}/${FB_PAGE}?fields=id,name,access_token&access_token=${encodeURIComponent(FB_TOKEN)}`);
 const j=await r.json();
 if(!r.ok)throw new Error(`Facebook page token lookup ${JSON.stringify(j)}`);
 if(String(j.id)!==String(FB_PAGE))throw new Error(`FACEBOOK_PAGE_ID uyusmuyor: env=${FB_PAGE} api=${j.id}`);
 if(!j.access_token)throw new Error("Facebook Page access_token dondurmedi; pages_show_list/pages_manage_posts yetkilerini kontrol edin");
 return String(j.access_token);
}
async function publishFacebook(d:any,bytes:Uint8Array){
 const pageAccessToken=await facebookPageToken();
 const fd=new FormData();fd.set("access_token",pageAccessToken);fd.set("caption",pubCaption(d,false));fd.set("published","true");fd.set("source",new Blob([bytes],{type:"image/jpeg"}),"fiyatzade.jpg");
 const r=await fetch(`https://graph.facebook.com/${FB_VER}/${FB_PAGE}/photos`,{method:"POST",body:fd});const j=await r.json();
 if(!r.ok)throw new Error(`Facebook photo publish ${JSON.stringify(j)}`);
 const postId=j.post_id||j.id;if(!postId)throw new Error(`Facebook post id dondurmedi: ${JSON.stringify(j)}`);return String(postId);
}
async function doPublish(id:string,msg:any){
 await ensureRows(id);const d=await candidate(id);const bytes=await adminPhotoBytes(msg);
 for(const p of ["telegram","instagram","facebook"]){
  const s=await state(id,p);if(s?.status==="published")continue;
  try{await mark(id,p,"publishing");const out=p==="telegram"?await publishTelegram(d,bytes):p==="instagram"?await publishInstagram(d,bytes):await publishFacebook(d,bytes);await mark(id,p,"published",out)}
  catch(e){await mark(id,p,"failed",undefined,String(e).slice(0,1000));console.error(p,e)}
 }
}
Deno.serve(async(req)=>{
 if(req.method!=="POST")return new Response("ok");
 if(WEBHOOK_SECRET && req.headers.get("x-telegram-bot-api-secret-token")!==WEBHOOK_SECRET)return new Response("forbidden",{status:403});
 const u=await req.json();const q=u.callback_query;if(!q)return new Response("ok");
 const raw=String(q.data||"");const [action,id]=raw.split(":",2);
 if(!id||!["publish","reject"].includes(action)){await ack(q.id,"Bilinmeyen işlem");return new Response("ok")}
 if(action==="reject"){await sb.from("deal_candidates").update({status:"rejected",updated_at:new Date().toISOString()}).eq("id",id);await sb.from("deal_publications").update({status:"failed",error_message:"Rejected by admin",updated_at:new Date().toISOString()}).eq("deal_candidate_id",id).in("status",["pending","publishing"]);await ack(q.id,"REDDET kaydedildi.");return new Response("ok")}
 await ack(q.id,"PAYLAŞ işlemi başlatıldı.");
 EdgeRuntime.waitUntil(doPublish(id,q.message));
 return new Response("ok");
});