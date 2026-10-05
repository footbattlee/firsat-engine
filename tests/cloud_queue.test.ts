import test from 'node:test';
import assert from 'node:assert/strict';
import {slotKey,allowedUrl,samePath,products,verifiedOffer,validateGap,xml,discountPresentation} from '../supabase/functions/publication-queue/core.ts';
test('Istanbul window, half hour slots and no catch-up',()=>{
 for(const s of ['2026-10-04T06:59:00Z','2026-10-04T21:00:00Z','2026-10-04T07:05:00Z','2026-10-04T07:29:00Z'])assert.equal(slotKey(new Date(s)),null);
 for(const s of ['2026-10-04T07:00:00Z','2026-10-04T20:30:00Z'])assert.equal(slotKey(new Date(s)),s.replace('Z','.000Z'));
 assert.equal(slotKey(new Date('2026-10-04T07:31:00Z')),'2026-10-04T07:30:00.000Z');
});
test('domains and redirect identity',()=>{
 assert.equal(allowedUrl('https://www.amazon.com.tr/dp/X','amazon'),true);
 for(const url of ['http://www.amazon.com.tr/dp/X','https://amazon.com.tr.evil.example/dp/X','https://x:pw@amazon.com.tr/dp/X','https://amazon.com.tr:444/dp/X'])assert.equal(allowedUrl(url,'amazon'),false);
 assert.equal(samePath('https://www.trendyol.com/old-p-123','https://www.trendyol.com/new-p-123','trendyol'),true);
 assert.equal(samePath('https://www.trendyol.com/old-p-123','https://www.trendyol.com/new-p-456','trendyol'),false);
});
const product={'@type':'Product',name:'ACME Model X',offers:{'@type':'Offer',price:'100',priceCurrency:'TRY',availability:'https://schema.org/InStock'}};
test('recommended product nodes do not qualify',()=>{assert.deepEqual(products({'@type':'ItemList',itemListElement:[product]}),[]);assert.equal(products({'@graph':[product]}).length,1);});
test('strict unique live TRY and stock evidence',()=>{
 assert.equal(verifiedOffer([product],'hepsiburada').price,100);
 for(const fields of [{price:0},{price:'NaN'},{priceCurrency:'USD'},{availability:'https://schema.org/OutOfStock'},{availability:undefined},{itemCondition:'https://schema.org/UsedCondition'},{'@type':'AggregateOffer'}])assert.throws(()=>verifiedOffer([{...product,offers:{...product.offers,...fields}}],'trendyol'));
 assert.throws(()=>verifiedOffer([product,product],'trendyol'));
 assert.throws(()=>verifiedOffer([{...product,offers:[product.offers,product.offers]}],'trendyol'));
});
test('live advantage threshold and suspicious gaps',()=>{
 assert.equal(validateGap(100,125,{}),20);
 for(const [price,rival] of [[100,101],[100,100],[1,100],[NaN,100],[100,Infinity]])assert.throws(()=>validateGap(price,rival,{}));
 assert.throws(()=>validateGap(100,125,{history_drop_percent:80}));
});
test('SVG data is escaped',()=>assert.equal(xml('<x & "y">'),'&lt;x &amp; &quot;y&quot;&gt;'));


test('automatic publication uses completed scan snapshot and never calls storefront detail',async()=>{
 const {readFileSync}=await import('node:fs');
 const code=readFileSync(new URL('../supabase/functions/publication-queue/index.ts',import.meta.url),'utf8');
 const candidateBody=code.slice(code.indexOf('async function candidate(id:string)'),code.indexOf('function tracked('));
 assert.ok(candidateBody.includes('Number(d.cheapest_price)'));
 assert.ok(candidateBody.includes('Number(d.competitor_price)'));
 assert.ok(candidateBody.includes('scan-not-complete'));
 assert.ok(!candidateBody.includes('await detail('));
 assert.ok(!candidateBody.includes('fetch('));
});

test('repeat discount uses previous sent price and a strict fifteen percent floor',()=>{
 const d={cheapest_price:850,competitor_price:1200,notification_reason:'redispatch_price_drop',previous_notified_price:1000,redispatch_drop_percent:29.17};
 const view=discountPresentation(d);
 assert.equal(view.percent,15);assert.equal(view.comparisonPrice,1000);assert.equal(view.repeat,true);
 assert.equal(validateGap(850,1200,d),29.17);
 for(const price of [851,950,1000,1100])assert.throws(()=>discountPresentation({...d,cheapest_price:price}));
 assert.throws(()=>discountPresentation({...d,previous_notified_price:null}));
});
