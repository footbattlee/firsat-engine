import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {encodeShareCode,decodeShareCode,brandedLink,captionHasDeal} from "../web/lib/share-links.mjs";
import {GET,HEAD} from "../web/app/f/[code]/route.ts";
const deal="11111111-1111-4111-8111-111111111111",offer="22222222-2222-4222-8222-222222222222";
test("public share code round-trips both exact identifiers and is URL safe",()=>{
 const code=encodeShareCode(deal,offer);assert.equal(code.length,43);assert.match(code,/^[A-Za-z0-9_-]+$/);
 assert.deepEqual(decodeShareCode(code),{deal,offer});
 assert.equal(decodeShareCode(code.slice(0,-1)+"J"),null);
 for(const input of ["bad","../",code+"=",code+"a",encodeURIComponent("💩")])assert.equal(decodeShareCode(input),null);
 assert.throws(()=>encodeShareCode("bad",offer));
});
test("all channels keep attribution through the existing tracker",async()=>{
 for(const source of ["telegram","instagram","facebook","story","whatsapp","other","bogus"]){
  const url=brandedLink({id:deal,offer_id:offer},source);
  assert.equal(new URL(url).hostname,"xn--frsatc-p9af.com");assert.ok(!url.includes("supabase"));
  const response=await GET(new Request(url+"&next=https://evil.example"),{params:Promise.resolve({code:encodeShareCode(deal,offer)})});
  assert.equal(response.status,302);assert.equal(response.headers.get("cache-control"),"no-store");
  const target=new URL(response.headers.get("location"));assert.equal(target.origin,"https://cmexmobjpeavlppmffqi.supabase.co");
  assert.deepEqual(Object.fromEntries(target.searchParams),{deal,offer,channel:source==="bogus"?"other":source});
 }
});
test("HEAD resolves without fetching or counting a click; malformed links fail closed",async()=>{
 const original=globalThis.fetch;globalThis.fetch=()=>{throw Error("route must not proxy the visitor");};
 try{
  const response=await HEAD(new Request("https://xn--frsatc-p9af.com/f/"+encodeShareCode(deal,offer),{method:"HEAD"}),{params:Promise.resolve({code:encodeShareCode(deal,offer)})});
  assert.equal(response.status,302);
  assert.equal((await GET(new Request("https://xn--frsatc-p9af.com/f/bad"),{params:Promise.resolve({code:"bad"})})).status,404);
 }finally{globalThis.fetch=original;}
});
test("Instagram recovery identifies new links and old captions without substring collisions",()=>{
 assert.equal(captionHasDeal("Go "+brandedLink({id:deal,offer_id:offer},"instagram"),deal),true);
 assert.equal(captionHasDeal("Go https://example.test/?deal="+deal+"&offer="+offer,deal),true);
 assert.equal(captionHasDeal("Go "+brandedLink({id:offer,offer_id:deal},"instagram"),deal),false);
 assert.equal(captionHasDeal("Go "+brandedLink({id:deal,offer_id:offer},"instagram").replace("fırsatcı.com","evil.example"),deal),false);
 assert.equal(captionHasDeal("Go https://example.test/?deal="+deal+"2",deal),false);
});
test("web and edge deployments use the same code format",()=>{
 assert.equal(readFileSync(new URL("../web/lib/share-links.mjs",import.meta.url),"utf8").replaceAll("\r",""),readFileSync(new URL("../supabase/functions/_shared/share-links.mjs",import.meta.url),"utf8").replaceAll("\r",""));
});
