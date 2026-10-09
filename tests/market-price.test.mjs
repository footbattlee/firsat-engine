import test from "node:test";
import assert from "node:assert/strict";
import {priceFacts,PURCHASE_CHECK_AGE_MS} from "../web/lib/market-price.ts";
const now=Date.parse("2026-10-09T20:30:00Z");
const row={catalogue_active:true,title:"Product",status:"verified",merchant_slug:"amazon",product_url:"https://www.amazon.com.tr/dp/B08S7QYCKQ",price:800,price_checked_at:"2026-10-09T20:00:00Z",competitor_price:1000,competitor_checked_at:"2026-10-09T19:00:00Z",old_price:1200,old_checked_at:"2026-10-08T20:00:00Z",recorded_price:780,recorded_checked_at:"2026-10-09T18:00:00Z"};
test("history drop and competitor advantage stay independent",()=>{const f=priceFacts(row,now);assert.equal(f.dropPercent,33.33);assert.equal(f.gapPercent,20);assert.equal(f.savings,400);assert.equal(priceFacts({...row,competitor_checked_at:null},now).gapPercent,null);});
test("stale prices never become a current opportunity and invalid history cannot make a badge",()=>{const f=priceFacts({...row,price_checked_at:new Date(now-PURCHASE_CHECK_AGE_MS).toISOString()},now);assert.equal(f.price,null);assert.equal(f.dropPercent,null);assert.equal(f.recordedPrice,780);for(const patch of [{old_checked_at:row.price_checked_at},{old_checked_at:"2026-09-01"},{old_price:810},{old_price:5000},{catalogue_active:false},{price_checked_at:new Date(now+60000).toISOString()}])assert.equal(priceFacts({...row,...patch},now).dropPercent,null);});
test("stock failures suppress live price but a dated scan may remain in catalogue",()=>{assert.equal(priceFacts({...row,status:"ended"},now).price,null);assert.equal(priceFacts({...row,recorded_checked_at:"2026-09-01"},now).recordedPrice,null);assert.equal(priceFacts({...row,product_url:"https://evil.example"},now).price,null);});

test("discount threshold uses the actual percentage before display rounding",()=>{
 const now=Date.parse("2026-10-09T12:00:00Z");
 const row={catalogue_active:true,status:"verified",title:"Product",product_url:"https://www.amazon.com.tr/dp/B08S7QYCKQ",merchant_slug:"amazon",price:850.01,price_checked_at:new Date(now-1000).toISOString(),old_price:1000,old_checked_at:new Date(now-86400000).toISOString(),competitor_price:1000,competitor_checked_at:new Date(now-1000).toISOString()};
 assert.equal(priceFacts(row,now).dropPercent,null);assert.equal(priceFacts(row,now).gapPercent,null);
 assert.equal(priceFacts({...row,price:850},now).dropPercent,15);
});
