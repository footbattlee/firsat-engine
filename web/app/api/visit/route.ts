import {recordTraffic} from "../../../lib/traffic";
export const dynamic="force-dynamic";
export const runtime="nodejs";
export async function POST(req:Request) {
 const origin=req.headers.get("origin");
 if(!origin||origin!==new URL(req.url).origin)return new Response(null,{status:403});
 // Only this homepage is instrumented; public callers cannot invent product events.
 if(!req.headers.get("content-type")?.startsWith("application/json"))return new Response(null,{status:415});
 const body=await req.text();
 if(body.length>100)return new Response(null,{status:413});
 let parsed;try{parsed=JSON.parse(body);}catch{return new Response(null,{status:400});}
 if(parsed?.path!=="/")return new Response(null,{status:400});
 await recordTraffic(req,"pageview","/");
 return new Response(null,{status:204,headers:{"Cache-Control":"no-store"}});
}
