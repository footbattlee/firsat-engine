import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const env=(name:string)=>Deno.env.get(name)?.trim()||"";
const BOT=env("TELEGRAM_BOT_TOKEN");
const CHAT_ID=env("TELEGRAM_APPROVAL_CHAT_ID");
const SUPABASE_URL=env("SUPABASE_URL");
const SERVICE_KEY=env("SUPABASE_SERVICE_ROLE_KEY")||(()=>{try{return JSON.parse(env("SUPABASE_SECRET_KEYS")).default||""}catch{return ""}})();
const sb=createClient(SUPABASE_URL,SERVICE_KEY);
const TG_API="https://api.telegram.org/bot"+BOT;
const MEDIA_BUCKET=env("INSTAGRAM_MEDIA_BUCKET")||"instagram-media";

const escapeHtml=(v:any)=>String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
const ranked=(m:Map<string,number>,limit:number)=>[...m.entries()].sort((a,b)=>b[1]-a[1]).slice(0,limit);

async function reportText(days:number){
 const {data,error}=await sb.rpc("get_click_report",{p_days:days,p_complete_days:true});
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
 const lines=["📊 <b>"+days+" Günlük Tıklama Raporu</b>","👆 Toplam tekil gerçek tıklama: <b>"+total+"</b>"];
 if(!total){lines.push("Henüz kaydedilmiş gerçek tıklama yok.");return lines.join("\n")}
 const ch=ranked(channels,10);if(ch.length)lines.push("",...ch.map(([k,v])=>"• "+escapeHtml(k)+": <b>"+v+"</b>"));
 const ms=ranked(merchants,5);if(ms.length)lines.push("","<b>Mağazalar</b>",...ms.map(([k,v],i)=>(i+1)+". "+escapeHtml(k)+" — "+v));
 const ps=ranked(products,10);if(ps.length)lines.push("","<b>En çok tıklanan ürünler</b>",...ps.map(([k,v],i)=>(i+1)+". "+escapeHtml(k).slice(0,100)+" — "+v));
 return lines.join("\n").slice(0,4090);
}
function istanbulParts(){
 const fmt=new Intl.DateTimeFormat("en-CA",{timeZone:"Europe/Istanbul",year:"numeric",month:"2-digit",day:"2-digit",weekday:"short",hour:"2-digit",minute:"2-digit",hourCycle:"h23"});
 return Object.fromEntries(fmt.formatToParts(new Date()).filter(p=>p.type!=="literal").map(p=>[p.type,p.value])) as Record<string,string>;
}
async function send(text:string){
 const r=await fetch(TG_API+"/sendMessage",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({chat_id:CHAT_ID,text,parse_mode:"HTML",disable_web_page_preview:true})});
 const j=await r.json();if(!j.ok)throw new Error("Telegram sendMessage: "+JSON.stringify(j));
}
async function cleanupOldReels(){
 const cutoff=new Date(Date.now()-7*24*60*60*1000).toISOString();
 const {data,error}=await sb.from("deal_publications").select("deal_candidate_id").eq("platform","reel").in("status",["pending","failed"]).lt("updated_at",cutoff).limit(1000);
 if(error)throw error;
 const ids=[...new Set((data||[]).map((row:any)=>String(row.deal_candidate_id)))];
 if(!ids.length)return 0;
 const paths=ids.map(id=>"deals/"+id+"/reel.mp4");
 const {error:removeError}=await sb.storage.from(MEDIA_BUCKET).remove(paths);
 if(removeError)throw removeError;
 const {error:updateError}=await sb.from("deal_publications").update({status:"failed",error_message:"Hazırlanan Reels videosu 7 günlük saklama süresi sonunda silindi.",updated_at:new Date().toISOString()}).eq("platform","reel").in("deal_candidate_id",ids);
 if(updateError)throw updateError;
 return ids.length;
}

Deno.serve(async(req)=>{
 if(req.method!=="POST")return new Response("ok");
 if(!BOT||!CHAT_ID||!SERVICE_KEY)return new Response("report configuration missing",{status:500});
 const body=await req.json().catch(()=>({}));
 const schedule=String(body.schedule||"");
 if(!["daily","weekly"].includes(schedule))return new Response("bad request",{status:400});
 const p=istanbulParts(),hour=Number(p.hour),minute=Number(p.minute);
 const allowed=schedule==="daily"?hour===0&&minute>=1&&minute<=5:p.weekday==="Sun"&&hour===8&&minute<=5;
 if(!allowed)return new Response("outside schedule window",{status:403});
 const periodKey=schedule+":"+p.year+"-"+p.month+"-"+p.day;
 const {data:existing}=await sb.from("click_report_dispatches").select("status").eq("period_key",periodKey).maybeSingle();
 if(existing?.status==="sent")return new Response("already sent");
 const {error:claimError}=await sb.from("click_report_dispatches").upsert({period_key:periodKey,report_type:schedule,status:"sending",updated_at:new Date().toISOString()},{onConflict:"period_key"});
 if(claimError)throw claimError;
 try{
  if(schedule==="daily"){
   const removed=await cleanupOldReels();
   if(removed)console.log("old reel assets removed",removed);
  }
  const days=schedule==="daily"?1:7;
  await send(await reportText(days));
  await sb.from("click_report_dispatches").update({status:"sent",sent_at:new Date().toISOString(),error_message:null,updated_at:new Date().toISOString()}).eq("period_key",periodKey);
  return new Response("sent");
 }catch(e){
  await sb.from("click_report_dispatches").update({status:"failed",error_message:String(e).slice(0,1000),updated_at:new Date().toISOString()}).eq("period_key",periodKey);
  console.error(e);return new Response("failed",{status:500});
 }
});
