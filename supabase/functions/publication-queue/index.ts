import 'jsr:@supabase/functions-js/edge-runtime.d.ts';
import {createClient} from 'npm:@supabase/supabase-js@2.57.4';
import {parseHTML} from 'npm:linkedom@0.18.12';
import {allowedUrl,samePath,products,verifiedOffer,validateGap,slotKey,discountPresentation} from './core.ts';
import {artwork} from './artwork.ts';
import {fetchProductImage} from './image.ts';
import {caption,apiJSON,DeliveryError,deliverChannels,matchingMedia} from './delivery.ts';
const env=(n:string)=>Deno.env.get(n)?.trim()||'';
const service=env('SUPABASE_SERVICE_ROLE_KEY')||(()=>{try{return JSON.parse(env('SUPABASE_SECRET_KEYS')).default||'';}catch{return '';}})();
const url=env('SUPABASE_URL'),sb=createClient(url,service);
const bucket=env('INSTAGRAM_MEDIA_BUCKET')||'instagram-media';
const igBase=env('INSTAGRAM_GRAPH_BASE')||'https://graph.instagram.com',igToken=env('INSTAGRAM_ACCESS_TOKEN'),igUser=env('INSTAGRAM_USER_ID');
const publicChat=env('TELEGRAM_PUBLISH_CHAT_ID'),fbToken=env('FACEBOOK_SYSTEM_USER_TOKEN'),fbPage=env('FACEBOOK_PAGE_ID'),fbVersion=env('FACEBOOK_GRAPH_VERSION')||'v26.0';
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
 const queued=await checked(await sb.from('publication_queue').select('notification_context').eq('candidate_id',id).maybeSingle());
 if(queued?.notification_context)Object.assign(d,queued.notification_context);
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
         cheapest_price:price,competitor_price:competitor,gap_percent:gap,notification_reason:d.notification_reason,previous_notified_price:d.previous_notified_price,redispatch_drop_percent:d.redispatch_drop_percent,image_url:cheap.image_url,price_checked_at:batch.completed_at};
}
function tracked(d:any){return url+'/functions/v1/deal-click?'+new URLSearchParams({deal:d.id,offer:d.offer_id,channel:'story'});}
async function image(d:any){return fetchProductImage(d.image_url);}
async function prepare(d:any,slot:string){
 const photo=await image(d);const post=await artwork(d,photo.bytes,photo.type),story=await artwork(d,photo.bytes,photo.type,true);
 const tag=slot.replace(/[^\d]/g,'');const base=`deals/${d.id}/queue-${tag}`;
 for(const [path,bytes] of [[base+'-post.png',post],[base+'-story.png',story]] as [string,Uint8Array][]){
  await checked(await sb.storage.from(bucket).upload(path,bytes,{contentType:'image/png',upsert:true}));
 }
 return {...d,publication_slot:slot,post_path:base+'-post.png',post_url:sb.storage.from(bucket).getPublicUrl(base+'-post.png').data.publicUrl,story_path:base+'-story.png'};
}

async function graph(path:string,body?:URLSearchParams){
 return apiJSON(fetch,igBase+'/'+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+igToken,...(body?{'Content-Type':'application/x-www-form-urlencoded'}:{})},body},body?90000:20000);
}
async function instagram(d:any,container?:string){
 let id=container;
 if(!id){
  const j=await graph(igUser+'/media',new URLSearchParams({image_url:d.post_url,caption:caption(d,url,'instagram')}));
  if(!j.id)throw new DeliveryError('instagram-container-missing',false,true);
  id=String(j.id);
  await checked(await sb.from('deal_publications').update({container_id:id,updated_at:new Date().toISOString()}).eq('deal_candidate_id',d.id).eq('platform','instagram'));
 }
 for(let i=0;i<12;i++){
  const status=await graph(id+'?fields=status_code');
  if(status.status_code==='FINISHED'){
   // Persist the point after which a timeout must be reconciled, never republished.
   const requested=new Date().toISOString();
   const reservation=await checked(await sb.from('deal_publications').update({publish_requested_at:requested}).eq('deal_candidate_id',d.id).eq('platform','instagram').eq('status','publishing').is('publish_requested_at',null).select('id'));
   if(!reservation.length)throw new DeliveryError('instagram-publish-already-requested',false,true);
   let out:any;
   try{out=await graph(igUser+'/media_publish',new URLSearchParams({creation_id:id}));}
   catch(e){
    if(e instanceof DeliveryError&&!e.ambiguous)await checked(await sb.from('deal_publications').update({publish_requested_at:null}).eq('deal_candidate_id',d.id).eq('platform','instagram').eq('publish_requested_at',requested));
    throw e;
   }
   if(!out.id)throw new DeliveryError('instagram-result-missing',false,true);
   return String(out.id);
  }
  if(['ERROR','EXPIRED'].includes(status.status_code))throw new DeliveryError('instagram-container-failed');
  await new Promise(resolve=>setTimeout(resolve,3000));
 }
 throw new DeliveryError('instagram-container-not-ready',true);
}
function originalSlot(d:any){
 if(d.publication_slot)return d.publication_slot;
 const digits=String(d.post_url||'').match(/queue-(\d{14})/);
 if(!digits)return '';
 const v=digits[1];return v.slice(0,4)+'-'+v.slice(4,6)+'-'+v.slice(6,8)+'T'+v.slice(8,10)+':'+v.slice(10,12)+':'+v.slice(12,14)+'Z';
}
function dispatchDelivery(id:string){
 // A separate invocation gives each platform its own execution time budget.
 EdgeRuntime.waitUntil(fetch(url+'/functions/v1/publication-queue',{
  method:'POST',headers:{Authorization:'Bearer '+service,'Content-Type':'application/json'},
  body:JSON.stringify({mode:'deliver',candidate_id:id}),signal:AbortSignal.timeout(120000)
 }).then(r=>{if(!r.ok)console.error('publication-delivery-dispatch-failed',r.status);}).catch(()=>console.error('publication-delivery-dispatch-unavailable')));
}
async function confirmInstagram(q:any,out:string,timestamp=new Date().toISOString()){
 await checked(await sb.from('deal_publications').update({status:'published',external_post_id:out,published_at:timestamp,error_message:null,updated_at:new Date().toISOString()}).eq('deal_candidate_id',q.candidate_id).eq('platform','instagram').eq('status','publishing'));
 await checked(await sb.from('publication_queue').update({state:'published',last_error:null,updated_at:new Date().toISOString()}).eq('candidate_id',q.candidate_id).in('state',['held','publishing']));
 dispatchDelivery(q.candidate_id);
}
async function reconcileInstagram(allowResume=false){
 const hour=Number(new Intl.DateTimeFormat("en-US",{timeZone:"Europe/Istanbul",hour:"numeric",hourCycle:"h23"}).format(new Date()));
 allowResume=allowResume&&hour>=10&&hour<=23;
 if(!igToken||!igUser)return 0;
 const settings=await checked(await sb.from('publication_queue_settings').select('source_after').eq('id',true).single());
 const rows=await checked(await sb.from('publication_queue').select('*').in('state',['held','publishing']).not('snapshot','is',null).gte('source_run_started_at',settings.source_after||'1970-01-01T00:00:00Z').lt('updated_at',new Date(Date.now()-120000).toISOString()).limit(30));
 if(!rows.length)return 0;
 let media:any[];
 try{media=(await graph(igUser+'/media?fields=id,caption,timestamp,media_type&limit=100' )).data||[];}catch{media=[];}
 let count=0,resumed=0;
 for(const q of rows){
  const p=await checked(await sb.from('deal_publications').select('status,container_id,publish_requested_at,external_post_id,published_at').eq('deal_candidate_id',q.candidate_id).eq('platform','instagram').maybeSingle());
  if(p?.status==='published'&&p.external_post_id){await confirmInstagram(q,p.external_post_id,p.published_at);count++;continue;}
  if(p?.status!=='publishing')continue;
  const matches=matchingMedia(media,q.candidate_id,p.publish_requested_at||originalSlot(q.snapshot));
  if(matches.length===1){await confirmInstagram(q,String(matches[0].id),matches[0].timestamp);count++;continue;}
  // A saved container can be resumed only if media_publish was never requested.
  if(allowResume&&p.container_id&&!p.publish_requested_at&&resumed<1&&Date.now()-Date.parse(originalSlot(q.snapshot))<=600000){
   resumed++;
   try{const id=await instagram(q.snapshot,p.container_id);await confirmInstagram(q,id);count++;}catch(e){await checked(await sb.from('deal_publications').update({error_message:e instanceof DeliveryError?e.code:'instagram-outcome-unknown',updated_at:new Date().toISOString()}).eq('deal_candidate_id',q.candidate_id).eq('platform','instagram'));}
  }
 }
 return count;
}
async function facebookPageToken(){
 if(!fbToken||!fbPage)throw new DeliveryError('facebook-configuration-missing',true);
 let j:any;
 try{j=await apiJSON(fetch,'https://graph.facebook.com/'+fbVersion+'/'+fbPage+'?'+new URLSearchParams({fields:'id,name,access_token',access_token:fbToken}),{},20000);}
 catch(e){throw new DeliveryError(e instanceof DeliveryError?e.code:'facebook-token-unavailable',true);}
 if(String(j.id)!==fbPage||!j.access_token)throw new DeliveryError('facebook-page-token-missing',true);
 return String(j.access_token);
}
async function sendChannel(platform:string,d:any){
 if(platform==='facebook'){
  const token=await facebookPageToken();
  const fd=new FormData();fd.set('access_token',token);fd.set('url',d.post_url);fd.set('caption',caption(d,url,'facebook'));fd.set('published','true');
  const j=await apiJSON(fetch,'https://graph.facebook.com/'+fbVersion+'/'+fbPage+'/photos',{method:'POST',body:fd},90000);
  if(!j.id)throw new DeliveryError('facebook-result-missing',false,true);
  return String(j.post_id||j.id);
 }
 const chat=platform==='story'?storyChat:publicChat;
 if(!bot||!chat)throw new DeliveryError(platform+'-configuration-missing',true);
 const fd=new FormData();fd.set('chat_id',chat);
 if(platform==='story'){
  const {data,error}=await sb.storage.from(bucket).download(d.story_path);
  if(error||!data)throw new DeliveryError('story-file-unavailable',true);
  fd.set('document',data,'story.png');fd.set('caption',`📱 STORY HAZIR — gönderi yayınlandı\n\n${String(d.title).slice(0,400)}\n\n🔗 Ürüne git: ${tracked(d)}`);
 }else{
  // Upload the owned PNG directly. Asking Telegram to fetch a remote image
  // added a second network hop and caused long/ambiguous sendPhoto responses.
  const imageUrl=new URL(d.post_url),prefix='/storage/v1/object/public/'+bucket+'/';
  if(imageUrl.origin!==new URL(url).origin||!imageUrl.pathname.startsWith(prefix+'deals/'+d.id+'/'))throw new DeliveryError('telegram-photo-path-invalid');
  const path=decodeURIComponent(imageUrl.pathname.slice(prefix.length));
  const {data,error}=await sb.storage.from(bucket).download(path);
  if(error||!data)throw new DeliveryError('telegram-photo-unavailable',true);
  fd.set('photo',data,'fiyatzade.png');fd.set('caption',caption(d,url,'telegram'));
 }
 const j=await apiJSON(fetch,'https://api.telegram.org/bot'+bot+'/'+(platform==='story'?'sendDocument':'sendPhoto'),{method:'POST',body:fd},60000);
 if(!j.result?.message_id)throw new DeliveryError(platform+'-result-missing',false,true);
 return String(j.result.message_id);
}
async function deliverAll(q:any){
 return deliverChannels(q,{
  claim:(id:string,platform:string)=>rpc('claim_publication_channel',{p_id:id,p_platform:platform}),
  finish:(id:string,platform:string,claim:string,result:any)=>rpc('finish_publication_channel',{p_id:id,p_platform:platform,p_claim:claim,p_result:result}),
  send:sendChannel
 });
}
async function run(recoveryOnly=false){
 const settings=await checked(await sb.from('publication_queue_settings').select('*').eq('id',true).single());
 if(!settings.enabled||Date.now()<new Date(settings.not_before||0).getTime())return {status:'waiting',reason:'scheduled-start'};
 const recovered=await reconcileInstagram(recoveryOnly);
 const deliveries=[];
 const waiting=recoveryOnly&&recovered===0?await rpc('pending_publication_deliveries',{p_limit:1}):[];
 for(const q of waiting)deliveries.push({candidate_id:q.candidate_id,results:await deliverAll(q)});
 if(recoveryOnly)return {status:'recovered',reconciled:recovered,deliveries};
 if(!igToken||!igUser)throw Error('instagram-configuration-missing');
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
   await updateQueue(q,{state:'published',last_error:null});q.snapshot=d;
  }catch(e){const reason=e instanceof DeliveryError?e.code:'instagram-outcome-unknown';await checked(await sb.from('deal_publications').update({error_message:reason,updated_at:new Date().toISOString()}).eq('deal_candidate_id',q.candidate_id).eq('platform','instagram'));await updateQueue(q,{state:'held',last_error:'Instagram outcome requires review: '+reason});return {status:'held',candidate_id:q.candidate_id,reason};}
  await rpc('ensure_publication_channels',{p_id:q.candidate_id});dispatchDelivery(q.candidate_id);
  return {status:'published',candidate_id:q.candidate_id,deliveries:'scheduled'};
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
   if(!body.candidate_id)return Response.json({error:'candidate_id-required'},{status:400});
   const d=await candidate(String(body.candidate_id)),photo=await image(d);
   const png=await artwork(d,photo.bytes,photo.type,body.story===true);
   return new Response(png,{headers:{'Content-Type':'image/png','Cache-Control':'no-store'}});
  }
  if(body.dry_run){
   let query=sb.from('publication_queue').select('candidate_id').eq('state','queued').order('enqueued_at').limit(3);
   if(body.candidate_id)query=query.eq('candidate_id',String(body.candidate_id));
   const rows=await checked(await query);const results=[];
   for(const q of rows){try{const d=await candidate(q.candidate_id);const photo=await image(d);const png=await artwork(d,photo.bytes,photo.type);results.push({id:d.id,status:'verified',image_bytes:png.length});}catch(e){results.push({id:q.candidate_id,status:'unverified',reason:String(e).slice(0,160)});}}
   return Response.json({dry_run:true,slot:slotKey(new Date()),results,published:0});
  }
  if(body.mode==='configuration-test'){
   const targets:any={instagram:!!(igToken&&igUser),telegram:!!(bot&&publicChat),story:!!(bot&&storyChat),facebook:!!(fbToken&&fbPage)};
   for(const [name,chat] of [['telegram',publicChat],['story',storyChat]])if(bot&&chat){try{const j=await apiJSON(fetch,'https://api.telegram.org/bot'+bot+'/getChat?'+new URLSearchParams({chat_id:chat}));targets[name]={configured:true,title:j.result.title};}catch(e){targets[name]={configured:true,error:(e as Error).message};}}
   if(fbToken&&fbPage){try{await facebookPageToken();targets.facebook={configured:true,verified:true};}catch(e){targets.facebook={configured:true,error:(e as Error).message};}}
   return Response.json({targets,published:0});
  }
  if(body.mode==='deliver'){
   const q=await checked(await sb.from('publication_queue').select('*').eq('candidate_id',String(body.candidate_id)).eq('state','published').not('snapshot','is',null).single());
   return Response.json({candidate_id:q.candidate_id,deliveries:await deliverAll(q)});
  }
  return Response.json(await run(body.mode==='recover'));
 }catch(e){console.error('publication-queue',String(e));return Response.json({error:'queue-worker-failed'},{status:500});}
});