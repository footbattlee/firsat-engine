import test from 'node:test';
import assert from 'node:assert/strict';
import {caption,apiJSON,DeliveryError,deliverChannels,matchingMedia} from '../supabase/functions/publication-queue/delivery.ts';
const d={id:'00000000-0000-0000-0000-000000000001',offer_id:'offer',title:'Ürün',merchant:'Mağaza',cheapest_price:850,competitor_price:1200,notification_reason:'redispatch_price_drop',previous_notified_price:1000};
test('all platform captions show the actual repeat price drop and their tracking channel',()=>{
 for(const channel of ['instagram','telegram','facebook']){
  const text=caption(d,'https://example.test',channel);
  assert.ok(text.includes('Önceki paylaşım fiyatı: 1.000 TL'));
  assert.ok(text.includes('%15,00 düştü'));
  assert.ok(text.includes('channel='+channel));
  assert.ok(text.length<=1024);
 }
});
test('one channel failure does not suppress another; published channels cannot be resent',async()=>{
 const states=new Map([['story','pending'],['telegram','pending'],['facebook','published']]);
 const sends:string[]=[];
 const deps={claim:async(_id:string,p:string)=>{if(states.get(p)!=='pending')return null;states.set(p,'publishing');return p;},
  send:async(p:string)=>{sends.push(p);if(p==='story')throw new DeliveryError('api-rejected:429',true,false,120);return '123';},
  finish:async(_id:string,p:string,_claim:string,result:any)=>{states.set(p,result.status);if(p==='story')assert.ok(Number.isFinite(Date.parse(result.next_attempt_at)));return true;}};
 const out=await deliverChannels({candidate_id:d.id,snapshot:d},deps);
 assert.deepEqual(sends,['story','telegram']);assert.equal(out[1].status,'published');
 sends.length=0;await deliverChannels({candidate_id:d.id,snapshot:d},deps);assert.equal(sends.length,0);
});
test('ambiguous send is held instead of blindly resent',async()=>{
 let result:any;
 await deliverChannels({candidate_id:d.id,snapshot:d},{claim:async(_id:string,p:string)=>p==='story'?'token':null,
 send:async()=>{throw new DeliveryError('network-outcome-unknown',false,true);},
 finish:async(_id:string,_p:string,_token:string,r:any)=>{result=r;}});
 assert.equal(result.status,'failed');assert.equal(result.next_attempt_at,'infinity');
});
test('API rejection records a safe error code and retry interval without secrets',async()=>{
 const fetcher=async()=>Response.json({ok:false,error_code:429,description:'secret-token',parameters:{retry_after:42}},{status:429});
 await assert.rejects(()=>apiJSON(fetcher as typeof fetch,'https://example.test'),e=>{
  assert.ok(e instanceof DeliveryError);assert.equal(e.code,'api-rejected:429');assert.equal(e.retryAfter,42);assert.equal(e.ambiguous,false);return true;});
});
test('Instagram reconciliation requires exact candidate ID, image type and original slot',()=>{
 const row={id:'media',caption:'go https://x.test/?deal='+d.id+'&offer=x',timestamp:'2026-10-06T10:00:01Z',media_type:'IMAGE'};
 assert.equal(matchingMedia([row],d.id,'2026-10-06T10:00:00Z').length,1);
 for(const changed of [{...row,caption:row.caption.replace(d.id,d.id+'2')},{...row,media_type:'VIDEO'},{...row,timestamp:'2026-10-05T10:00:00Z'}])
  assert.equal(matchingMedia([changed],d.id,'2026-10-06T10:00:00Z').length,0);
});

test('a slow Instagram response can be reconciled while an older slot cannot',()=>{
 const row={id:'media',caption:'https://x/?deal='+d.id+'&offer=x',timestamp:'2026-10-06T10:06:00Z',media_type:'IMAGE'};
 assert.equal(matchingMedia([row],d.id,'2026-10-06T10:00:00Z').length,1);
 assert.equal(matchingMedia([row],d.id,'2026-10-06T09:30:00Z').length,0);
});
