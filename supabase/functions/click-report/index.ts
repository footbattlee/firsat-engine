import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.57.4";
import { formatClickReport } from "../_shared/click-report.mjs";

const env=(name:string)=>Deno.env.get(name)?.trim()||"";
const BOT=env("TELEGRAM_BOT_TOKEN");
const CHAT_ID=env("TELEGRAM_APPROVAL_CHAT_ID");
const SUPABASE_URL=env("SUPABASE_URL");
const SERVICE_KEY=env("SUPABASE_SERVICE_ROLE_KEY")||(()=>{try{return JSON.parse(env("SUPABASE_SECRET_KEYS")).default||""}catch{return ""}})();
const sb=createClient(SUPABASE_URL,SERVICE_KEY);
const TG_API="https://api.telegram.org/bot"+BOT;


async function reportText(days:number){
 const {data,error}=await sb.rpc("get_click_report_v3",{p_days:days,p_complete_days:true});
 if(error)throw error;
 return formatClickReport(data);
}
function istanbulParts(){
 const fmt=new Intl.DateTimeFormat("en-CA",{timeZone:"Europe/Istanbul",year:"numeric",month:"2-digit",day:"2-digit",weekday:"short",hour:"2-digit",minute:"2-digit",hourCycle:"h23"});
 return Object.fromEntries(fmt.formatToParts(new Date()).filter(p=>p.type!=="literal").map(p=>[p.type,p.value])) as Record<string,string>;
}
async function send(text:string){
 const r=await fetch(TG_API+"/sendMessage",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({chat_id:CHAT_ID,text,parse_mode:"HTML",disable_web_page_preview:true})});
 const j=await r.json();if(!j.ok)throw new Error("Telegram sendMessage: "+JSON.stringify(j));
}
Deno.serve(async(req)=>{
 const token=req.headers.get("x-publication-queue-token")||"";
 const auth=token.length===64?await sb.rpc("check_publication_queue_token",{p_token:token}):{data:false};
 if(!auth.data)return new Response("unauthorized",{status:401});
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
  const days=schedule==="daily"?1:7;
  await send(await reportText(days));
  await sb.from("click_report_dispatches").update({status:"sent",sent_at:new Date().toISOString(),error_message:null,updated_at:new Date().toISOString()}).eq("period_key",periodKey);
  return new Response("sent");
 }catch(e){
  await sb.from("click_report_dispatches").update({status:"failed",error_message:String(e).slice(0,1000),updated_at:new Date().toISOString()}).eq("period_key",periodKey);
  console.error(e);return new Response("failed",{status:500});
 }
});
