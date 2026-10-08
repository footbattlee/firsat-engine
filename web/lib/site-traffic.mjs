import {createHmac,createHash} from "node:crypto";
export function trafficKind(headers,eventType) {
 const ua=headers.get("user-agent")||"";
 const purpose=["purpose","sec-purpose","x-purpose"].map(k=>headers.get(k)||"").join(" ");
 if(/bot|crawler|spider|preview|facebookexternalhit|headlesschrome|whatsapp/i.test(ua))return "bot";
 if(/prefetch|prerender|preview/i.test(purpose))return "prefetch";
 if(eventType==="pageview") return ua && headers.get("sec-fetch-site")==="same-origin"
  && ["same-origin","cors"].includes(headers.get("sec-fetch-mode")) && headers.get("sec-fetch-dest")==="empty" ? "client_view" : "unverified";
 return headers.get("sec-fetch-mode")==="navigate" && headers.get("sec-fetch-dest")==="document"
  && headers.get("sec-fetch-user")==="?1" ? "navigation" : "unverified";
}
export function trafficEvent(headers,eventType,path,secret,now=new Date()) {
 const day=new Intl.DateTimeFormat("en-CA",{timeZone:"Europe/Istanbul",year:"numeric",month:"2-digit",day:"2-digit"}).format(now);
 const ip=(headers.get("x-forwarded-for")||"").split(",")[0].trim();
 const ua=(headers.get("user-agent")||"").slice(0,500);
 const visitor=createHmac("sha256",secret).update(day+"|"+ip+"|"+ua).digest("hex");
 const kind=trafficKind(headers,eventType);
 return {event_key:createHash("sha256").update([day,eventType,path,visitor,kind].join("|")).digest("hex"),
  event_type:eventType,path,visitor_hash:visitor,request_kind:kind};
}
