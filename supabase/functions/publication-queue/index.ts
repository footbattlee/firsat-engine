import 'jsr:@supabase/functions-js/edge-runtime.d.ts';
import {createClient} from 'npm:@supabase/supabase-js@2.57.4';
import {parseHTML} from 'npm:linkedom@0.18.12';
import {allowedUrl,samePath,products,verifiedOffer,validateGap,slotKey} from './core.ts';
import {artwork} from './artwork.ts';
const env=(n:string)=>Deno.env.get(n)?.trim()||'';
const service=env('SUPABASE_SERVICE_ROLE_KEY')||(()=>{try{return JSON.parse(env('SUPABASE_SECRET_KEYS')).default||'';}catch{return '';}})();
const url=env('SUPABASE_URL'),sb=createClient(url,service);
const bucket=env('INSTAGRAM_MEDIA_BUCKET')||'instagram-media';
const igBase=env('INSTAGRAM_GRAPH_BASE')||'https://graph.instagram.com',igToken=env('INSTAGRAM_ACCESS_TOKEN'),igUser=env('INSTAGRAM_USER_ID');
const storyChat=env('TELEGRAM_STORY_CHAT_ID')||env('TELEGRAM_APPROVAL_CHAT_ID'),bot=env('TELEGRAM_BOT_TOKEN');
async function checked(result:any){if(result.error)throw result.error;return result.data;}
async function rpc(name:string,args={}){return checked(await sb.rpc(name,args));}
async function updateQueue(q:any,values:any){await checked(await sb.from('publication_queue').update({...values,updated_at:new Date().toISOString()}).eq('candidate_id',q.candidate_id).eq('claim_token',q.claim_token));}
const headers={'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8','Referer':'https://www.google.com/','Cache-Control':'max-age=0','User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36','Accept-Language':'tr-TR,tr;q=0.9,en;q=0.8'};
async function detail(o:any,slug:string){
 let current=o.product_url;
 for(let i=0;i<4;i++){
  if(!allowedUrl(current,slug))throw Error('unexpected-product-domain');
  const r=await fetch(current,{headers,redirect:'manual',signal:AbortSignal.timeout(12000)});
  if(r.status>=300&&r.status<400){current=new URL(r.headers.get('location')||'',current).href;continue;}
  if(!r.ok||!samePath(o.product_url,current,slug))throw Error('product-http-or-identity-unverified:'+slug+':'+r.status);
  const {document}=parseHTML(await r.text());
  if(slug==='amazon'){
   if(document.querySelector('input#ASIN')?.getAttribute('value')!==o.merchant_product_id)throw Error('amazon-identity-unverified');
   const stock=document.querySelector('#availability')?.textContent?.toLowerCase()||'';
   const raw=document.querySelector('#corePrice_feature_div .a-price .a-offscreen, #corePriceDisplay_desktop_feature_div .a-price .a-offscreen, #apex_desktop .a-price .a-offscreen')?.textContent||'';
   const price=Number(raw.replace(/[^\d,]/g,'').replace(',','.'));
   if(!stock.includes('stokta')||stock.includes('yok')||!Number.isFinite(price)||price<=0)throw Error('amazon-stock-price-unverified:'+JSON.stringify({stock:stock.slice(0,150),rawPrice:raw.slice(0,80),schema:Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map((x:any)=>x.textContent?.slice(0,1000)),availabilityNodes:Array.from(document.querySelectorAll('[id*="availability"]')).map((x:any)=>({id:x.id,text:x.textContent?.slice(0,150)})),pageTitle:document.querySelector('title')?.textContent?.slice(0,100)}));
   return {price,title:document.querySelector('#productTitle')?.textContent||'',gtin:''};
  }
  const nodes:any[]=[];
  for(const script of document.querySelectorAll('script[type="application/ld+json"]')){try{nodes.push(...products(JSON.parse(script.textContent||'')));}catch{/* ignore invalid script */}}
  return verifiedOffer(nodes,slug);
 }
 throw Error('redirect-limit');
}
async function candidate(id:string){
 const d=await checked(await sb.from('deal_candidates').select('*').eq('id',id).eq('status','candidate').single());
 const settings=await checked(await sb.from('publication_queue_settings').select('source_after').eq('id',true).single());
 if(!d.scan_started_at||new Date(d.scan_started_at)<new Date(settings.source_after||0))throw Error('excluded-previous-scan');
 const batch=await checked(await sb.from('publication_scan_batches').select('completed_at').eq('started_at',d.scan_started_at).single());
 if(!batch.completed_at)throw Error('scan-not-complete');
 const offers=await checked(await sb.from('offers').select('*').in('id',[d.cheapest_offer_id,d.competitor_offer_id]));
 if(offers.length!==2||offers[0].merchant_id===offers[1].merchant_id)throw Error('distinct-offers-required');
 const variants=await checked(await sb.from('product_variants').select('id,product_id,gtin').in('id',offers.map((o:any)=>o.product_variant_id)).eq('active',true));
 const matches=await checked(await sb.from('product_matches').select('product_id').eq('canonical_product_id',d.canonical_product_id).eq('status','approved'));
 const approved=new Set(matches.map((m:any)=>m.product_id));
 if(offers.some((o:any)=>!approved.has(variants.find((v:any)=>v.id===o.product_variant_id)?.product_id)))throw Error('match-no-longer-approved');
 const merchants=await checked(await sb.from('merchants').select('id,name,slug').in('id',offers.map((o:any)=>o.merchant_id)));
 // Publishing uses the completed scan's price snapshot. The owner explicitly
 // approved skipping storefront availability and live price calls at publication.
 const cheap=offers.find((o:any)=>o.id===d.cheapest_offer_id);
 const price=Number(d.cheapest_price),competitor=Number(d.competitor_price);
 const gap=validateGap(price,competitor,d);
 const cp=await checked(await sb.from('canonical_products').select('title').eq('id',d.canonical_product_id).eq('active',true).single());
 if(!cp.title||!cheap.image_url)throw Error('creative-data-missing');
 const current=await checked(await sb.from('deal_candidates').select('status').eq('id',id).single());if(current.status!=='candidate')throw Error('candidate-rejected');
 return {id,offer_id:cheap.id,title:cp.title,merchant:merchants.find((m:any)=>m.id===cheap.merchant_id).name,
         cheapest_price:price,competitor_price:competitor,gap_percent:gap,image_url:cheap.image_url,price_checked_at:batch.completed_at};
}
function tracked(d:any){return url+'/functions/v1/deal-click?'+new URLSearchParams({deal:d.id,offer:d.offer_id,channel:'story'});}
async function image(d:any){
 const u=new URL(d.image_url),host=u.hostname;
 const allowed=['dsmcdn.com','hepsiburada.net','media-amazon.com','ssl-images-amazon.com','n11scdn.akamaized.net','n11.com','vatanbilgisayar.com','mediamarkt.com.tr','mmst.eu','mmsrg.com'];
 if(u.protocol!=='https:'||!allowed.some(h=>host===h||host.endsWith('.'+h)))throw Error('image-domain-unverified');
 const r=await fetch(u,{headers,signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('image-unavailable');
 const bytes=new Uint8Array(await r.arrayBuffer());if(bytes.length>8*1024*1024)throw Error('image-too-large');
 const type=(r.headers.get('content-type')||'').split(';')[0];
 if(!['image/jpeg','image/png','image/webp'].includes(type))throw Error('image-format-unverified');
 return {bytes,type};
}
async function prepare(d:any,slot:string){
 const photo=await image(d);const post=await artwork(d,photo.bytes,photo.type),story=await artwork(d,photo.bytes,photo.type,true);
 const tag=slot.replace(/[^\d]/g,'');const base=`deals/${d.id}/queue-${tag}`;
 for(const [path,bytes] of [[base+'-post.png',post],[base+'-story.png',story]] as [string,Uint8Array][]){
  await checked(await sb.storage.from(bucket).upload(path,bytes,{contentType:'image/png',upsert:true}));
 }
 return {...d,post_url:sb.storage.from(bucket).getPublicUrl(base+'-post.png').data.publicUrl,story_path:base+'-story.png'};
}
const money=(v:any)=>new Intl.NumberFormat('tr-TR',{maximumFractionDigits:2}).format(v)+' TL';
async function instagram(d:any){
 const caption=`🔥 FİYATZADE FIRSATI\n\n${d.title}\n\n🛒 ${d.merchant}\n💸 Rakip fiyat: ${money(d.competitor_price)}\n🔥 Fırsat fiyatı: ${money(d.cheapest_price)}\n📉 Rakipten %${d.gap_percent} daha ucuz\n\n🔗 Fırsata git: ${url}/functions/v1/deal-click?${new URLSearchParams({deal:d.id,offer:d.offer_id,channel:'instagram'})}\n\nFiyat bilgisi son taramaya aittir; fiyat ve stok değişebilir.\n#işbirliği #reklam #indirim #fırsat`;
 async function graph(path:string,body?:URLSearchParams){
  const r=await fetch(igBase+'/'+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+igToken,...(body?{'Content-Type':'application/x-www-form-urlencoded'}:{})},body,signal:AbortSignal.timeout(20000)});
  const j=await r.json();if(!r.ok)throw Error('instagram-api-failed');return j;
 }
 const j=await graph(igUser+'/media',new URLSearchParams({image_url:d.post_url,caption}));if(!j.id)throw Error('instagram-container-missing');
 for(let i=0;i<12;i++){
  const status=await graph(j.id+'?fields=status_code');
  if(status.status_code==='FINISHED'){
   const out=await graph(igUser+'/media_publish',new URLSearchParams({creation_id:String(j.id)}));if(!out.id)throw Error('instagram-result-missing');return String(out.id);
  }
  if(['ERROR','EXPIRED'].includes(status.status_code))throw Error('instagram-container-failed');
  await new Promise(resolve=>setTimeout(resolve,3000));
 }
 throw Error('instagram-container-timeout');
}
async function story(d:any){
 const {data,error}=await sb.storage.from(bucket).download(d.story_path);if(error)throw Error('story-file-unavailable');
 const fd=new FormData();fd.set('chat_id',storyChat);fd.set('caption',`📱 STORY HAZIR — gönderi yayınlandı\n\n${String(d.title).slice(0,400)}\n\n🔗 Ürüne git: ${tracked(d)}`);
 fd.set('document',data,'story.png');
 const r=await fetch(`https://api.telegram.org/bot${bot}/sendDocument`,{method:'POST',body:fd,signal:AbortSignal.timeout(20000)});
 const j=await r.json();if(!j.ok)throw Error('story-delivery-failed');return String(j.result.message_id);
}
async function deliverStory(q:any){
 const state=await checked(await sb.from('deal_publications').select('status').eq('deal_candidate_id',q.candidate_id).eq('platform','story').maybeSingle());
 if(state?.status!=='pending')return;
 const claimed=await checked(await sb.from('deal_publications').update({status:'publishing',updated_at:new Date().toISOString()}).eq('deal_candidate_id',q.candidate_id).eq('platform','story').eq('status','pending').select('id'));
 if(!claimed.length)return;
 try{
  const out=await story(q.snapshot);
  await checked(await sb.from('deal_publications').update({status:'published',external_post_id:out,published_at:new Date().toISOString()}).eq('deal_candidate_id',q.candidate_id).eq('platform','story'));
 }catch{
  // Ambiguous Telegram timeouts are held for inspection instead of resent.
  await checked(await sb.from('publication_queue').update({last_error:'story-delivery-requires-review'}).eq('candidate_id',q.candidate_id));
 }
}
async function run(){
 const settings=await checked(await sb.from('publication_queue_settings').select('*').eq('id',true).single());
 if(!settings.enabled||Date.now()<new Date(settings.not_before||0).getTime())return {status:'waiting',reason:'scheduled-start'};
 if(!igToken||!igUser||!bot||!storyChat)throw Error('publisher-configuration-missing');
 // Recover known successful Instagram publications before handling a new slot.
 const pendingStories=await checked(await sb.from('deal_publications').select('deal_candidate_id').eq('platform','story').eq('status','pending').limit(1000));
 const storyIds=pendingStories.map((p:any)=>p.deal_candidate_id);
 const recovery=storyIds.length?await checked(await sb.from('publication_queue').select('*').in('state',['published','publishing']).in('candidate_id',storyIds).not('snapshot','is',null).gte('source_run_started_at',settings.source_after||'1970-01-01T00:00:00Z').limit(10)):[];
 for(const q of recovery){
  const p=await checked(await sb.from('deal_publications').select('status').eq('deal_candidate_id',q.candidate_id).eq('platform','instagram').maybeSingle());
  if(p?.status==='published'&&q.snapshot){await checked(await sb.from('publication_queue').update({state:'published'}).eq('candidate_id',q.candidate_id));await deliverStory(q);}
 }
 await checked(await sb.from('publication_queue').update({state:'held',last_error:'Interrupted Instagram publication requires review'}).eq('state','publishing').lt('updated_at',new Date(Date.now()-600000).toISOString()));
 const slot=await rpc('start_publication_slot');if(!slot)return {status:'waiting'};
 const deadline=Date.now()+85000;
 for(let attempt=0;attempt<20&&Date.now()<deadline;attempt++){
  const rows=await rpc('claim_publication_item',{p_slot:slot});if(!rows.length)return {status:'empty'};const q=rows[0];
  let d:any;
  try{d=await candidate(q.candidate_id);d=await prepare(d,slot);}
  catch(e){await updateQueue(q,{state:'queued',next_check_at:new Date(Date.now()+1800000).toISOString(),last_error:String(e).slice(0,160)});continue;}
  const begin=await rpc('begin_publication',{p_id:q.candidate_id,p_claim:q.claim_token,p_slot:slot,p_snapshot:d});
  if(!begin){await updateQueue(q,{state:'queued',next_check_at:new Date(Date.now()+1800000).toISOString(),last_error:'publication-not-reserved'});continue;}
  try{
   const out=await instagram(d);
   await checked(await sb.from('deal_publications').update({status:'published',external_post_id:out,published_at:new Date().toISOString(),updated_at:new Date().toISOString()}).eq('deal_candidate_id',q.candidate_id).eq('platform','instagram'));
   await updateQueue(q,{state:'published',last_error:null});q.snapshot=d;await deliverStory(q);
   return {status:'published',candidate_id:q.candidate_id};
  }catch(e){await updateQueue(q,{state:'held',last_error:'Instagram outcome requires review'});return {status:'held',candidate_id:q.candidate_id};}
 }
 return {status:'unverified'};
}
Deno.serve(async(req)=>{
 if(req.method!=='POST')return new Response('method not allowed',{status:405});
 const bearer=req.headers.get('authorization')||'';
 let authorized=bearer==='Bearer '+service&&!!service;
 if(!authorized&&bearer.startsWith('Bearer ')&&bearer.length>30){
  // Verify alternate legacy/rotated service credentials via a service-only RPC.
  const probe=await createClient(url,bearer.slice(7)).rpc('check_publication_queue_token',{p_token:''});
  authorized=!probe.error;
 }
 if(!authorized){const token=req.headers.get('x-publication-queue-token')||'';if(token.length===64)authorized=!!await rpc('check_publication_queue_token',{p_token:token});}
 if(!authorized)return new Response('unauthorized',{status:401});
 try{
  const body=await req.json().catch(()=>({}));
  if(body.mode==='connection-test'){
   const dc=await checked(await sb.from('deal_candidates').select('cheapest_offer_id,competitor_offer_id').eq('id',String(body.candidate_id)).single());
   const offers=await checked(await sb.from('offers').select('*').in('id',[dc.cheapest_offer_id,dc.competitor_offer_id]));
   const merchants=await checked(await sb.from('merchants').select('id,slug').in('id',offers.map((o:any)=>o.merchant_id)));
   const results=[];
   for(const offer of offers){const slug=merchants.find((m:any)=>m.id===offer.merchant_id)?.slug;try{const info=await detail(offer,slug);results.push({store:slug,status:'verified',price:info.price});}catch(e){results.push({store:slug,status:'unverified',reason:String(e).slice(0,400)});}}
   return Response.json({connection_test:true,results,published:0});
  }
  if(body.mode==='render-test'){
   const bytes=Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAN0lEQVR4nO3RwQ0AMAjDwJT9d05HMB9+vgGCZF7bXJrT9XhgwR8gEyETIRMhEyETIRMhEyEThXzH8QM9OMM6fAAAAABJRU5ErkJggg=='),c=>c.charCodeAt(0));
   const png=await artwork({title:'Güncel fiyat kontrolü — Türkçe görsel testi',merchant:'Mağaza',cheapest_price:1234.56,competitor_price:1599.99,gap_percent:22.84},bytes,'image/png');
   return new Response(png,{headers:{'Content-Type':'image/png'}});
  }
  if(body.dry_run){
   let query=sb.from('publication_queue').select('candidate_id').eq('state','queued').order('enqueued_at').limit(3);
   if(body.candidate_id)query=query.eq('candidate_id',String(body.candidate_id));
   const rows=await checked(await query);const results=[];
   for(const q of rows){try{const d=await candidate(q.candidate_id);const photo=await image(d);const png=await artwork(d,photo.bytes,photo.type);results.push({id:d.id,status:'verified',image_bytes:png.length});}catch(e){results.push({id:q.candidate_id,status:'unverified',reason:String(e).slice(0,160)});}}
   return Response.json({dry_run:true,slot:slotKey(new Date()),results,published:0});
  }
  return Response.json(await run());
 }catch(e){console.error('publication-queue',String(e));return Response.json({error:'queue-worker-failed'},{status:500});}
});