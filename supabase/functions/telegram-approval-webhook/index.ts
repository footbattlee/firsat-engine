import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const env=(n:string)=>Deno.env.get(n)?.trim()||"";
const BOT=env("TELEGRAM_BOT_TOKEN");
const TG_API=`https://api.telegram.org/bot${BOT}`;
const PUBLISH_CHAT_ID=env("TELEGRAM_PUBLISH_CHAT_ID");
const APPROVAL_CHAT_ID=env("TELEGRAM_APPROVAL_CHAT_ID");
const STORY_CHAT_ID=env("TELEGRAM_STORY_CHAT_ID")||APPROVAL_CHAT_ID;
const IG_TOKEN=env("INSTAGRAM_ACCESS_TOKEN");
const IG_USER=env("INSTAGRAM_USER_ID");
const IG_BASE=env("INSTAGRAM_GRAPH_BASE")||"https://graph.instagram.com";
const FB_TOKEN=env("FACEBOOK_SYSTEM_USER_TOKEN");
const FB_PAGE=env("FACEBOOK_PAGE_ID");
const FB_VER=env("FACEBOOK_GRAPH_VERSION")||"v26.0";
const WEBHOOK_SECRET=env("TELEGRAM_WEBHOOK_SECRET");
const BUCKET=env("INSTAGRAM_MEDIA_BUCKET")||"instagram-media";
const REELS_MAX_PER_DAY=Number(env("INSTAGRAM_REELS_MAX_PER_DAY")||"2");
const sbUrl=env("SUPABASE_URL");
const service=env("SUPABASE_SERVICE_ROLE_KEY") || (()=>{try{return JSON.parse(env("SUPABASE_SECRET_KEYS")).default||""}catch{return ""}})();
const sb=createClient(sbUrl,service);
const CLICK_BASE=sbUrl+"/functions/v1/deal-click";
function tracked(d:any,channel:string){
 const q=new URLSearchParams({deal:String(d.id),offer:String(d.offer_id),channel});
 return CLICK_BASE+"?"+q.toString();
}

async function tg(method:string, body:any) {
  const r=await fetch(`${TG_API}/${method}`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
  const j=await r.json(); if(!j.ok) throw new Error(`Telegram ${method}: ${JSON.stringify(j)}`); return j.result;
}
async function ack(id:string,text:string){try{await tg("answerCallbackQuery",{callback_query_id:id,text})}catch(e){console.error("ack",e)}}
const money=(v:any)=>new Intl.NumberFormat("tr-TR",{style:"currency",currency:"TRY",minimumFractionDigits:0,maximumFractionDigits:2}).format(Number(v));
function isRedispatch(d:any){return d.notification_reason==="redispatch_price_drop"}
function pubCaption(d:any,html=false,channel="other"){
 const repeat=isRedispatch(d);
 const gap=Number(repeat?d.redispatch_drop_percent:d.gap_percent).toFixed(2).replace(".",",");
 const oldLabel=repeat?"Önceki paylaşım fiyatı":"Rakip fiyat";
 const oldPrice=repeat?d.previous_notified_price:d.competitor_price;
 const discount=repeat?"Son paylaşımdan sonra %"+gap+" düştü":"Rakip mağazadan %"+gap+" daha ucuz";
 const title=String(d.title), merchant=String(d.merchant), link=tracked(d,channel);
 return `🔥 FİYATZADE FIRSATI\n\n${html?"<b>":""}${title}${html?"</b>":""}\n\n🛒 ${merchant}\n💸 ${oldLabel}: ${money(oldPrice)}\n🔥 Fırsat fiyatı: ${money(d.cheapest_price)}\n📉 ${discount}\n\n${html?`🔗 <a href="${link}">Fırsata Git</a>\n\n`:`🔗 Fırsata git: ${link}\n\n`}Fiyatlar değişebilir. Satın almadan önce mağaza fiyatını kontrol edin.\n\n#işbirliği #reklam #fiyatzade #indirim #fırsat`;
}
async function candidate(id:string){
 const {data,error}=await sb.from("deal_candidates").select("id,canonical_product_id,cheapest_offer_id,cheapest_merchant_id,gap_percent,cheapest_price,competitor_price,notification_reason,redispatch_drop_percent,previous_notified_price").eq("id",id).single();
 if(error) throw error;
 const [{data:cp,error:cpErr},{data:offer,error:offerErr},{data:merchant,error:merchantErr}]=await Promise.all([
   sb.from("canonical_products").select("title").eq("id",data.canonical_product_id).single(),
   sb.from("offers").select("product_url").eq("id",data.cheapest_offer_id).single(),
   sb.from("merchants").select("name").eq("id",data.cheapest_merchant_id).single()
 ]);
 if(cpErr) throw cpErr;if(offerErr) throw offerErr;if(merchantErr) throw merchantErr;
 return {id,offer_id:data.cheapest_offer_id,canonical_product_id:data.canonical_product_id,title:cp?.title||"-",merchant:merchant?.name||"-",gap_percent:data.gap_percent,cheapest_price:data.cheapest_price,competitor_price:data.competitor_price,notification_reason:data.notification_reason,redispatch_drop_percent:data.redispatch_drop_percent,previous_notified_price:data.previous_notified_price,product_url:offer?.product_url||""};
}
async function ensureRows(id:string){
 for(const platform of ["telegram","instagram","facebook","story"]){
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
 const fd=new FormData();fd.set("chat_id",PUBLISH_CHAT_ID);fd.set("caption",pubCaption(d,true,"telegram"));fd.set("parse_mode","HTML");fd.set("photo",new Blob([bytes],{type:"image/jpeg"}),"fiyatzade.jpg");
 const r=await fetch(`${TG_API}/sendPhoto`,{method:"POST",body:fd});const j=await r.json();if(!j.ok)throw new Error(JSON.stringify(j));return String(j.result.message_id);
}
async function publishStory(d:any){
 const path=`deals/${d.id}/story.png`;
 const imageUrl=sb.storage.from(BUCKET).getPublicUrl(path).data.publicUrl;
 const imageResponse=await fetch(imageUrl);
 if(!imageResponse.ok)throw new Error(`Story görseli bulunamadı: HTTP ${imageResponse.status}`);
 const bytes=new Uint8Array(await imageResponse.arrayBuffer());
 const fd=new FormData();fd.set("chat_id",STORY_CHAT_ID);fd.set("caption",`📱 STORY HAZIR\n\n${String(d.title)}\n\n🔗 Ürüne git: ${tracked(d,"story")}`);fd.set("photo",new Blob([bytes],{type:"image/png"}),"story.png");
 const r=await fetch(`${TG_API}/sendPhoto`,{method:"POST",body:fd});const j=await r.json();if(!j.ok)throw new Error(`Telegram story ${JSON.stringify(j)}`);return String(j.result.message_id);
}
async function uploadImage(id:string,bytes:Uint8Array){
 const path=`deals/${id}/webhook-instagram.jpg`;const {error}=await sb.storage.from(BUCKET).upload(path,bytes,{contentType:"image/jpeg",upsert:true});if(error)throw error;
 return sb.storage.from(BUCKET).getPublicUrl(path).data.publicUrl;
}
async function publishInstagram(d:any,bytes:Uint8Array){
 const imageUrl=await uploadImage(d.id,bytes);
 let r=await fetch(`${IG_BASE}/${IG_USER}/media`,{method:"POST",headers:{Authorization:`Bearer ${IG_TOKEN}`,"content-type":"application/x-www-form-urlencoded"},body:new URLSearchParams({image_url:imageUrl,caption:pubCaption(d,false,"instagram")})});
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
function reelCaption(d:any){
 const repeat=isRedispatch(d);
 const gap=Number(repeat?d.redispatch_drop_percent:d.gap_percent).toFixed(2).replace(".",",");
 const discount=repeat?"Son paylaşım fiyatına göre %"+gap+" düştü":"Rakip mağazadan %"+gap+" daha ucuz";
 return "🔥 BUGÜNÜN FIRSATI\n\n"+String(d.title)+"\n\n🛒 "+String(d.merchant)+"\n🔥 "+money(d.cheapest_price)+"\n📉 "+discount+"\n\nFırsatları kaçırmamak için @anlikindirimradari hesabını takip et.\n🔗 Telegram kanalı biyografide.\n\n#işbirliği #reklam #anlikindirimradari #indirim #fırsat #alışveriş";
}
async function sendReelAssist(d:any){
 const videoUrl=sb.storage.from(BUCKET).getPublicUrl("deals/"+d.id+"/reel.mp4").data.publicUrl;
 const videoResponse=await fetch(videoUrl);
 if(!videoResponse.ok)throw new Error("Hazır Reels videosu indirilemedi: HTTP "+videoResponse.status);
 const bytes=new Uint8Array(await videoResponse.arrayBuffer());
 const fd=new FormData();
 fd.set("chat_id",STORY_CHAT_ID);
 fd.set("caption","🎬 REELS VİDEOSU HAZIR\n\n"+String(d.title));
 fd.set("supports_streaming","true");
 fd.set("video",new Blob([bytes],{type:"video/mp4"}),"reels.mp4");
 const response=await fetch(TG_API+"/sendVideo",{method:"POST",body:fd});
 const result=await response.json();
 if(!result.ok)throw new Error("Telegram Reels videosu "+JSON.stringify(result));
 await tg("sendMessage",{
  chat_id:STORY_CHAT_ID,
  text:"📝 REELS AÇIKLAMASI — KOPYALA VE YAPIŞTIR\n\n"+reelCaption(d),
  disable_web_page_preview:true,
 });
}
function istanbulMidnightUtc(){
 const parts=new Intl.DateTimeFormat("en-CA",{timeZone:"Europe/Istanbul",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
 const values=Object.fromEntries(parts.filter(p=>p.type!=="literal").map(p=>[p.type,p.value]));
 return new Date(values.year+"-"+values.month+"-"+values.day+"T00:00:00+03:00").toISOString();
}
async function publishedReelsToday(){
 const {count,error}=await sb.from("deal_publications").select("deal_candidate_id",{count:"exact",head:true}).eq("platform","reel").eq("status","published").gte("published_at",istanbulMidnightUtc());
 if(error)throw error;return Number(count||0);
}
async function publishReel(d:any){
 const videoUrl=sb.storage.from(BUCKET).getPublicUrl("deals/"+d.id+"/reel.mp4").data.publicUrl;
 const check=await fetch(videoUrl,{method:"HEAD"});
 if(!check.ok)throw new Error("Hazır Reels videosu bulunamadı: HTTP "+check.status);
 let r=await fetch(IG_BASE+"/"+IG_USER+"/media",{method:"POST",headers:{Authorization:"Bearer "+IG_TOKEN,"content-type":"application/x-www-form-urlencoded"},body:new URLSearchParams({media_type:"REELS",video_url:videoUrl,caption:reelCaption(d),share_to_feed:"true"})});
 let j=await r.json();if(!r.ok||!j.id)throw new Error("IG Reels container "+JSON.stringify(j));
 const creationId=String(j.id);let last:any=null;
 for(let i=0;i<24;i++){
  await new Promise(resolve=>setTimeout(resolve,5000));
  const sr=await fetch(IG_BASE+"/"+creationId+"?fields=status_code,status&access_token="+encodeURIComponent(IG_TOKEN));
  const sj=await sr.json();last=sj;
  if(sj.status_code==="FINISHED")break;
  if(["ERROR","EXPIRED"].includes(String(sj.status_code)))throw new Error("IG Reels status "+JSON.stringify(sj));
 }
 if(last?.status_code!=="FINISHED")throw new Error("IG Reels container not ready "+JSON.stringify(last));
 r=await fetch(IG_BASE+"/"+IG_USER+"/media_publish",{method:"POST",headers:{Authorization:"Bearer "+IG_TOKEN,"content-type":"application/x-www-form-urlencoded"},body:new URLSearchParams({creation_id:creationId})});
 j=await r.json();if(!r.ok||!j.id)throw new Error("IG Reels publish "+JSON.stringify(j));return String(j.id);
}
async function ensureReelRow(id:string){
 const current=await state(id,"reel");
 if(!current){
  const {error}=await sb.from("deal_publications").insert({deal_candidate_id:id,platform:"reel",status:"pending",updated_at:new Date().toISOString()});
  if(error)throw error;
 }
}
async function doPublishReel(id:string){
 await ensureReelRow(id);
 const current=await state(id,"reel");if(current?.status==="published")return;
 if(await publishedReelsToday()>=REELS_MAX_PER_DAY){
  await mark(id,"reel","failed",undefined,"Günlük 2 Reels limiti dolu");return;
 }
 try{
  await mark(id,"reel","publishing");
  const d=await candidate(id);
  const out=await publishReel(d);
  await mark(id,"reel","published",out);
  try{await sendReelAssist(d)}catch(e){console.error("reel assist",e)}
 }catch(e){await mark(id,"reel","failed",undefined,String(e).slice(0,1000));console.error("reel",e)}
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
 const fd=new FormData();fd.set("access_token",pageAccessToken);fd.set("caption",pubCaption(d,false,"facebook"));fd.set("published","true");fd.set("source",new Blob([bytes],{type:"image/jpeg"}),"fiyatzade.jpg");
 const r=await fetch(`https://graph.facebook.com/${FB_VER}/${FB_PAGE}/photos`,{method:"POST",body:fd});const j=await r.json();
 if(!r.ok)throw new Error(`Facebook photo publish ${JSON.stringify(j)}`);
 const postId=j.post_id||j.id;if(!postId)throw new Error(`Facebook post id dondurmedi: ${JSON.stringify(j)}`);return String(postId);
}

const escapeHtml=(v:any)=>String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
function reportDays(text:string){
 const clean=text.trim();
 let m=clean.match(/^\/rapor(?:@\w+)?(?:\s+(\d+))?$/iu);
 if(m)return Math.min(90,Math.max(1,Number(m[1]||7)));
 m=clean.match(/^(\d+)\s+g[uü]nl[uü]k\s+rapor$/iu);
 return m?Math.min(90,Math.max(1,Number(m[1]))):null;
}
async function clickReport(days:number,completeDays=false){
 const {data,error}=await sb.rpc("get_click_report",{p_days:days,p_complete_days:completeDays});
 if(error)throw error;
 const rows=(data||[]) as any[];
 const total=rows.reduce((n,r)=>n+Number(r.clicks||0),0);
 const channels=new Map<string,number>(),merchants=new Map<string,number>(),products=new Map<string,number>();
 for(const r of rows){
  const count=Number(r.clicks||0);
  channels.set(String(r.channel||"other"),(channels.get(String(r.channel||"other"))||0)+count);
  merchants.set(String(r.merchant||"-"),(merchants.get(String(r.merchant||"-"))||0)+count);
  products.set(String(r.title||"-"),(products.get(String(r.title||"-"))||0)+count);
 }
 const ranked=(m:Map<string,number>,limit:number)=>[...m.entries()].sort((a,b)=>b[1]-a[1]).slice(0,limit);
 const lines=["📊 <b>"+days+" Günlük Tıklama Raporu</b>","👆 Toplam tekil gerçek tıklama: <b>"+total+"</b>"];
 if(!total){lines.push("Henüz kaydedilmiş gerçek tıklama yok.");return lines.join("\n")}
 const ch=ranked(channels,10);if(ch.length)lines.push("",...ch.map(([k,v])=>"• "+escapeHtml(k)+": <b>"+v+"</b>"));
 const ms=ranked(merchants,5);if(ms.length)lines.push("","<b>Mağazalar</b>",...ms.map(([k,v],i)=>(i+1)+". "+escapeHtml(k)+" — "+v));
 const ps=ranked(products,10);if(ps.length)lines.push("","<b>En çok tıklanan ürünler</b>",...ps.map(([k,v],i)=>(i+1)+". "+escapeHtml(k).slice(0,100)+" — "+v));
 return lines.join("\n").slice(0,4090);
}
async function sendClickReport(chatId:string,days:number,completeDays=false){
 await tg("sendMessage",{chat_id:chatId,text:await clickReport(days,completeDays),parse_mode:"HTML",disable_web_page_preview:true});
}

Deno.serve(async(req)=>{
 if(req.method!=="POST")return new Response("ok");
 if(WEBHOOK_SECRET && req.headers.get("x-telegram-bot-api-secret-token")!==WEBHOOK_SECRET)return new Response("forbidden",{status:403});
 const u=await req.json();
 const msg=u.message;
 if(msg?.text){
  const chatId=String(msg.chat?.id||"");
  if(!APPROVAL_CHAT_ID||chatId!==APPROVAL_CHAT_ID)return new Response("ok");
  const days=reportDays(String(msg.text));
  if(days!==null){
   try{await sendClickReport(chatId,days)}
   catch(e){console.error("click report",e);await tg("sendMessage",{chat_id:chatId,text:"Rapor hazırlanamadı: "+String(e).slice(0,500)})}
  }
  return new Response("ok");
 }
 const q=u.callback_query;if(!q)return new Response("ok");
 if(String(q.message?.chat?.id||"")!==APPROVAL_CHAT_ID)return new Response("forbidden",{status:403});
 const raw=String(q.data||"");const [action,id]=raw.split(":",2);
 if(!id||!["publish","reject","reel"].includes(action)){await ack(q.id,"Bilinmeyen işlem");return new Response("ok")}
 if(action==="reject"){await sb.from("deal_candidates").update({status:"rejected",updated_at:new Date().toISOString()}).eq("id",id);await sb.from("deal_publications").update({status:"failed",error_message:"Rejected by admin",updated_at:new Date().toISOString()}).eq("deal_candidate_id",id).in("status",["pending","publishing"]);await ack(q.id,"REDDET kaydedildi.");return new Response("ok")}
 if(action==="reel"){
  const current=await state(id,"reel");
  if(current?.status==="published"){await ack(q.id,"Bu ürünün Reels'i zaten paylaşıldı.");return new Response("ok")}
  if(await publishedReelsToday()>=REELS_MAX_PER_DAY){await ack(q.id,"Bugünkü 2 Reels limiti doldu.");return new Response("ok")}
  await ensureReelRow(id);
  await ack(q.id,"REELS paylaşımı başlatıldı.");
  EdgeRuntime.waitUntil(doPublishReel(id));
  return new Response("ok");
 }
 await ack(q.id,"Normal gönderi otomatik kuyrukta; yarım saatlik yayın sırasını bekliyor.");
 return new Response("ok");
});
