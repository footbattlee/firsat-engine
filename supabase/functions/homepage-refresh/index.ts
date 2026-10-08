import 'jsr:@supabase/functions-js/edge-runtime.d.ts';
import {createClient} from 'npm:@supabase/supabase-js@2.57.4';
import {parseHTML} from 'npm:linkedom@0.18.12';
import {allowedProduct,sameProduct,parsePrice,advantage} from './price.mjs';
const env=(n:string)=>Deno.env.get(n)?.trim()||'';
const base=env('SUPABASE_URL');
const service=env('SUPABASE_SERVICE_ROLE_KEY')||(()=>{try{return JSON.parse(env('SUPABASE_SECRET_KEYS')).default||'';}catch{return '';}})();
const sb=createClient(base,service);
async function data(q:any){const r=await q;if(r.error)throw r.error;return r.data;}
const headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36','Accept-Language':'tr-TR,tr;q=0.9','Cache-Control':'no-cache','Accept':'text/html,application/xhtml+xml','Referer':'https://www.google.com/','Cookie':'i18n-prefs=TRY; lc-acbtr=tr_TR'};
async function check(url:string,slug:string,debug=false){
 let current=url;
 for(let i=0;i<4;i++){
  if(!allowedProduct(current,slug))throw Error('product-domain-unverified');
  const r=await fetch(current,{headers,redirect:'manual',signal:AbortSignal.timeout(10000)});
  if(r.status>=300&&r.status<400){current=new URL(r.headers.get('location')||'',current).href;continue;}
  if(!r.ok)throw Error('store-http-'+r.status);
  if(!sameProduct(url,current,slug))throw Error('product-redirect-unverified');
  const html=await r.text();if(html.length>2500000)throw Error('page-too-large');
  const doc=parseHTML(html).document;
  for(const n of doc.querySelectorAll('style'))n.remove();
  try{return parsePrice(doc,slug,current);}catch(e){
   if(debug)throw Error(JSON.stringify({reason:e instanceof Error?e.message:'parse-failed',title:doc.querySelector('h1,#productTitle')?.textContent?.trim().slice(0,120),availability:doc.querySelector('#availability')?.textContent?.trim().slice(0,200),price:doc.querySelector('#corePrice_feature_div .a-price .a-offscreen,#corePriceDisplay_desktop_feature_div .a-price .a-offscreen')?.textContent?.trim().slice(0,60),availabilityNodes:[...doc.querySelectorAll('[id*=availability]')].slice(0,6).map((n:any)=>({id:n.id,text:n.textContent?.trim().slice(0,300)})),buybox:doc.querySelector('#buybox')?.textContent?.trim().slice(0,1000),apex:doc.querySelector('#apex_desktop')?.textContent?.trim().slice(0,500)}));
   throw e;
  }
 }
 throw Error('redirect-limit');
}
Deno.serve(async(req:Request)=>{
 if(req.method!=='POST')return new Response('method not allowed',{status:405});
 const token=req.headers.get('x-publication-queue-token')||'';
 const auth=token.length===64?await sb.rpc('check_publication_queue_token',{p_token:token}):{data:false};
 if(!auth.data)return new Response('unauthorized',{status:401});
 try{
  const body=await req.json().catch(()=>({}));
  const [candidates,manual,previous]=await Promise.all([
   data(sb.from('deal_candidates').select('*').eq('status','candidate').gte('gap_percent',15).lt('gap_percent',70).order('gap_percent',{ascending:false}).limit(60)),
   data(sb.from('homepage_manual_deals').select('*').eq('active',true).gt('expires_at',new Date().toISOString()).limit(30)),
   data(sb.from('homepage_deals').select('id,attempted_at')),
  ]);
  const active=new Set([...candidates.map((d:any)=>d.id),...manual.map((d:any)=>'manual-'+d.id)]);
  const removed=previous.filter((d:any)=>!active.has(d.id)).map((d:any)=>d.id);
  if(removed.length)await data(sb.from('homepage_deals').update({status:'ended',error_code:'listing-no-longer-active'}).in('id',removed));
  const last=new Map(previous.map((d:any)=>[d.id,Date.parse(d.attempted_at)]));
  const tasks=[...candidates.map((d:any)=>({id:d.id,d,manual:false})),...manual.map((d:any)=>({id:'manual-'+d.id,d,manual:true}))]
   .filter((t:any)=>!body.candidate_id||t.id===body.candidate_id)
   .sort((a:any,b:any)=>Number(last.get(a.id)||0)-Number(last.get(b.id)||0)).slice(0,9);
  const ids=[...new Set(tasks.filter((t:any)=>!t.manual).flatMap((t:any)=>[t.d.cheapest_offer_id,t.d.competitor_offer_id]))];
  const [offers,merchants,products]=await Promise.all([
   ids.length?data(sb.from('offers').select('*').in('id',ids)):[],
   data(sb.from('merchants').select('id,name,slug')),
   tasks.some((t:any)=>!t.manual)?data(sb.from('canonical_products').select('id,title,brand').in('id',tasks.filter((t:any)=>!t.manual).map((t:any)=>t.d.canonical_product_id)).eq('active',true)):[],
  ]);
  const variantIds=[...new Set(offers.map((o:any)=>o.product_variant_id).filter(Boolean))];
  const canonicalIds=[...new Set(tasks.filter((t:any)=>!t.manual).map((t:any)=>t.d.canonical_product_id))];
  const [variants,matches]=await Promise.all([
   variantIds.length?data(sb.from('product_variants').select('id,product_id,gtin').in('id',variantIds).eq('active',true)):[],
   canonicalIds.length?data(sb.from('product_matches').select('canonical_product_id,product_id').in('canonical_product_id',canonicalIds).eq('status','approved')):[],
  ]);
  const vm=new Map(variants.map((v:any)=>[v.id,v]));
  const approved=new Set(matches.map((x:any)=>x.canonical_product_id+':'+x.product_id));
  const om=new Map(offers.map((o:any)=>[o.id,o])),mm=new Map(merchants.map((m:any)=>[m.id,m])),pm=new Map(products.map((p:any)=>[p.id,p]));
  const results:any[]=[];let cursor=0;
  async function worker(){while(cursor<tasks.length){
   const t=tasks[cursor++],d=t.d;
   const cheap:any=t.manual?{product_url:d.product_url,affiliate_url:d.affiliate_url,image_url:d.image_url}:om.get(d.cheapest_offer_id);
   const m:any=t.manual?merchants.find((m:any)=>m.slug===d.merchant_slug):mm.get(cheap?.merchant_id);
   const p:any=t.manual?d:pm.get(d.canonical_product_id);
   if(!cheap||!m||!p){results.push({id:t.id,status:'missing-data'});await data(sb.from('homepage_deals').upsert({id:t.id,candidate_id:t.manual?null:d.id,manual_id:t.manual?d.id:null,offer_id:cheap?.id||null,title:p?.title||d.title||'Unavailable listing',merchant_slug:m?.slug||'unknown',merchant_name:m?.name||'Unknown',product_url:cheap?.product_url||'',status:'unverified',error_code:'missing-data',checked_at:null,attempted_at:new Date().toISOString()}));continue;}
   const row:any={id:t.id,candidate_id:t.manual?null:d.id,manual_id:t.manual?d.id:null,offer_id:t.manual?null:cheap.id,title:p.title,brand:p.brand||'',merchant_slug:m.slug,merchant_name:m.name,product_url:cheap.product_url,affiliate_url:cheap.affiliate_url||null,image_url:cheap.image_url||null,expires_at:t.manual?d.expires_at:null,attempted_at:new Date().toISOString(),status:'unverified',checked_at:null};
   try{
    if(!t.manual){
     const rival:any=om.get(d.competitor_offer_id);
     const cv:any=vm.get(cheap.product_variant_id),rv:any=vm.get(rival?.product_variant_id);
     if(!cv||!rv||!approved.has(d.canonical_product_id+':'+cv.product_id)||!approved.has(d.canonical_product_id+':'+rv.product_id))throw Error('match-no-longer-approved');
     if(cv.gtin&&rv.gtin&&cv.gtin!==rv.gtin)throw Error('variant-identity-mismatch');
    }
    const current=await check(cheap.product_url,m.slug,body.debug===true);row.price=current.price;row.title=current.title;
    if(!t.manual){
     const rival:any=om.get(d.competitor_offer_id),rm:any=mm.get(rival?.merchant_id);
     if(!rival||!rm||rm.id===m.id)throw Error('competitor-unverified');
     const live=await check(rival.product_url,rm.slug,body.debug===true);row.competitor_price=live.price;row.competitor_name=rm.name;
     row.status=advantage(current.price,live.price)===null?'ended':'verified';
     if(row.status==='ended')row.error_code='advantage-lost';
    }else row.status='verified';
    row.checked_at=new Date().toISOString();row.error_code=row.error_code||null;
   }catch(e){row.error_code=e instanceof Error?e.message.slice(0,120):'check-failed';if(body.debug===true)results.push({id:t.id,diagnostic:e instanceof Error?e.message:'failed'});}
   await data(sb.from('homepage_deals').upsert(row));results.push({id:t.id,status:row.status,price:row.price||null,error:row.error_code});
  }}
  await Promise.all([worker(),worker(),worker()]);
  return Response.json({checked:tasks.length,verified:results.filter(x=>x.status==='verified').length,results});
 }catch(e){console.error('homepage-refresh',e instanceof Error?e.message:'failed');return Response.json({error:'refresh-failed'},{status:500});}
});
