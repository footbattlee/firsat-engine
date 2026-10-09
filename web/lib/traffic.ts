import "server-only";
import {trafficEvent} from "./site-traffic.mjs";
const base=(process.env.SUPABASE_URL||"https://cmexmobjpeavlppmffqi.supabase.co").replace(/\/$/,"");
const key=process.env.SUPABASE_SERVICE_ROLE_KEY||"";
export async function recordTraffic(req:Request,type:"pageview"|"outbound",path:string,listingId?:string,merchant?:string) {
 if(req.method==="HEAD"||!key)return;
 // Local and deployment-preview verification must not inflate domain reports.
 if(!["xn--frsatc-p9af.com","www.xn--frsatc-p9af.com"].includes(new URL(req.url).hostname))return;
 const event=trafficEvent(req.headers,type,path,key);
 // Known automated previews do not enter the website counters.
 if(["bot","prefetch"].includes(event.request_kind))return;
 try {
  const response=await fetch(base+"/rest/v1/site_traffic_events?on_conflict=event_key",{
   method:"POST",headers:{apikey:key,Authorization:"Bearer "+key,"Content-Type":"application/json",
    Prefer:"resolution=ignore-duplicates,return=minimal"},
   body:JSON.stringify({...event,listing_id:listingId||null,merchant:merchant||null}),
   cache:"no-store",signal:AbortSignal.timeout(2000)
  });
  if(!response.ok)console.error("website traffic write failed",response.status);
 }catch{console.error("website traffic write unavailable");}
}
