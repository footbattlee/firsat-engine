import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire, stripTypeScriptTypes} from "node:module";
import {join} from "node:path";
import vm from "node:vm";
import {webcrypto} from "node:crypto";
import {requestMetadata} from "../supabase/functions/_shared/click-request.mjs";
import {formatClickReport} from "../supabase/functions/_shared/click-report.mjs";
const ua="Mozilla/5.0 Chrome/139.0.0.0 Safari/537.36";
const nav={"user-agent":ua,"sec-fetch-mode":"navigate","sec-fetch-dest":"document","sec-fetch-user":"?1"};
test("generic browser and Facebook referer are insufficient to claim navigation",()=>{
 assert.equal(requestMetadata(new Headers({"user-agent":ua,"referer":"https://m.facebook.com/"})).request_kind,"unverified");
 assert.equal(requestMetadata(new Headers()).request_kind,"unverified");
});
test("explicit navigation signal is recognized without calling it a person",()=>{
 assert.equal(requestMetadata(new Headers(nav)).request_kind,"navigation");
 assert.equal(requestMetadata(new Headers({...nav,"sec-fetch-user":"?0"})).request_kind,"unverified");
 assert.equal(requestMetadata(new Headers({...nav,"sec-fetch-dest":"iframe"})).request_kind,"unverified");
});
test("prefetch and known crawler override navigation headers",()=>{
 for(const key of ["purpose","sec-purpose","x-purpose"])
  assert.equal(requestMetadata(new Headers({...nav,[key]:"prefetch;prerender"})).request_kind,"prefetch");
 for(const user of ["facebookexternalhit/1.1","TelegramBot","Googlebot-Image","HeadlessChrome/139"])
  assert.equal(requestMetadata(new Headers({...nav,"user-agent":user})).is_bot,true);
});
async function handlerFixture(fn) {
 const records=[];let handler;
 const offer={id:"22222222-2222-4222-8222-222222222222",merchant_id:"merchant",affiliate_url:"https://www.amazon.com.tr/dp/test?tag=example-21"};
 const sb={from(table){return {select(){return this},eq(){return this},maybeSingle(){return Promise.resolve({data:table==="offers"?offer:{id:"deal"}})},insert(value){records.push(value);return Promise.resolve({error:null})}}}};
 const source=readFileSync(new URL("../supabase/functions/deal-click/index.ts",import.meta.url),"utf8").replace(/^import .*;\r?\n/gm,"");
 vm.runInNewContext(stripTypeScriptTypes(source),{Request,Response,URL,Intl,Date,TextEncoder,crypto:webcrypto,console,
  requestMetadata,createClient:()=>sb,Deno:{env:{get:()=>"test"},serve:fn=>{handler=fn}}});
 const url="https://test/functions/v1/deal-click?deal=11111111-1111-4111-8111-111111111111&offer="+offer.id+"&channel=facebook";
 await fn({handler,records,url});
}
test("browser GET records evidence and redirects without following the merchant",()=>handlerFixture(async({handler,records,url})=>{
 const res=await handler(new Request(url,{headers:nav}));
 assert.equal(res.status,302);assert.match(res.headers.get("location"),/^https:\/\/www.amazon.com.tr/);
 assert.equal(records.length,1);assert.equal(records[0].request_kind,"navigation");
 assert.equal(records[0].fetch_user,"?1");assert.equal(records[0].is_bot,false);
}));
test("crawler GET is recorded separately and stops before the affiliate redirect",()=>handlerFixture(async({handler,records,url})=>{
 const res=await handler(new Request(url,{headers:{"user-agent":"facebookexternalhit/1.1"}}));
 assert.equal(res.status,200);assert.equal(res.headers.get("location"),null);
 assert.equal(records[0].request_kind,"bot");assert.equal(records[0].is_bot,true);
}));
test("HEAD never creates a click; unknown GET still opens normally",()=>handlerFixture(async({handler,records,url})=>{
 assert.equal((await handler(new Request(url,{method:"HEAD",headers:nav}))).status,302);
 assert.equal(records.length,0);
 assert.equal((await handler(new Request(url,{headers:{"user-agent":ua}}))).status,302);
 assert.equal(records[0].request_kind,"unverified");
}));
const report={period_start:"2026-10-06T21:00:00Z",period_end:"2026-10-07T21:00:00Z",bot_requests:737,
 rows:[{channel:"facebook",merchant:"Amazon",title:"<Product>",clicks:0,unverified_clicks:69}]};
test("report explicitly covers October 7 in Istanbul, separately labels unknowns",()=>{
 const text=formatClickReport(report);
 assert.match(text,/0?7\.10\.2026 00:00/);assert.match(text,/0?8\.10\.2026 00:00/);
 assert.match(text,/Tarayıcı açılış sinyali olan: <b>0/);assert.match(text,/Belirsiz istek: <b>69/);
 assert.match(text,/kişi sayısı değildir/i);assert.match(text,/Amazon Gelir Ortaklığı verisi değildir/);
 assert.doesNotMatch(text,/gerçek tıklama/);
});
test("report escapes product names and stays within Telegram limits",()=>{
 const text=formatClickReport({...report,rows:[...report.rows,{channel:"telegram",merchant:"M<&",title:"<Product>",clicks:3,unverified_clicks:2}]});
 assert.match(text,/Tarayıcı açılış sinyali olan: <b>3/);assert.match(text,/Belirsiz istek: <b>71/);
 assert.match(text,/&lt;Product&gt;/);assert.match(text,/M&lt;&amp;/);assert.ok(text.length<=4096);
});
const require=createRequire(join(process.env.QUEUE_SQL_TEST_RUNTIME,"package.json"));
const {PGlite}=require("@electric-sql/pglite");
const id="11111111-1111-4111-8111-111111111111";
async function sqlFixture(fn) {
 const db=new PGlite();try{
  await db.exec(`
create role anon;create role authenticated;create role service_role;
create table public.canonical_products(id uuid primary key,title text);
create table public.merchants(id uuid primary key,name text);
create table public.deal_candidates(id uuid primary key,canonical_product_id uuid);
create table public.deal_publications(deal_candidate_id uuid,platform text,published_at timestamptz);
create table public.deal_click_events(id bigint generated always as identity primary key,deal_candidate_id uuid,merchant_id uuid,
 channel text,is_bot boolean default false,user_agent text,referer text,clicked_at timestamptz,visitor_hash text);
`);
  await db.exec(readFileSync(new URL("../supabase/migrations/20261008120000_classify_click_request_evidence.sql",import.meta.url),"utf8"));
  await db.query("insert into public.canonical_products values($1,'Product');",[id]);
  await db.query("insert into public.merchants values($1,'Amazon');",[id]);
  await db.query("insert into public.deal_candidates values($1,$1);",[id]);
  await fn(db);
 } finally {await db.close();}
}
const asOf="2026-10-08T00:01:00+03";
async function event(db,time,kind="unverified",visitor="v",bot=false) {
 await db.query("insert into public.deal_click_events(deal_candidate_id,merchant_id,channel,clicked_at,request_kind,visitor_hash,is_bot) values($1,$1,'facebook',$2,$3,$4,$5)",[id,time,kind,visitor,bot]);
}
async function readReport(db,complete=true) {
 return (await db.query("select public.get_click_report_v2(1,$1,$2) data",[complete,asOf])).rows[0].data;
}
test("SQL Istanbul complete-day boundaries include precisely Oct 7",()=>sqlFixture(async db=>{
 await event(db,"2026-10-06T23:59:59+03","navigation","before");
 await event(db,"2026-10-07T00:00:00+03","navigation","start");
 await event(db,"2026-10-07T23:59:59+03","navigation","end");
 await event(db,"2026-10-08T00:00:00+03","navigation","after");
 const r=await readReport(db);assert.equal(r.rows[0].clicks,2);
 assert.equal(new Date(r.period_start).toISOString(),"2026-10-06T21:00:00.000Z");
 assert.equal(new Date(r.period_end).toISOString(),"2026-10-07T21:00:00.000Z");
}));
test("SQL preserves legacy requests as unknown, excludes bots and prefetch",()=>sqlFixture(async db=>{
 await event(db,"2026-10-07T12:00:00+03");
 await event(db,"2026-10-07T12:01:00+03","bot","bot",true);
 await event(db,"2026-10-07T12:02:00+03","prefetch","pre");
 const r=await readReport(db);assert.equal(r.rows[0].clicks,0);assert.equal(r.rows[0].unverified_clicks,1);assert.equal(r.bot_requests,2);
}));
test("SQL repeats deduplicate; navigation upgrades unknown for the same daily product visitor",()=>sqlFixture(async db=>{
 await event(db,"2026-10-07T12:00:00+03");
 await event(db,"2026-10-07T12:01:00+03","navigation");
 await event(db,"2026-10-07T12:02:00+03","navigation");
 const r=await readReport(db);assert.equal(r.rows[0].clicks,1);assert.equal(r.rows[0].unverified_clicks,0);
}));
test("SQL genuine early navigation survives preview window; unknown early requests do not",()=>sqlFixture(async db=>{
 await db.query("insert into public.deal_publications values($1,'facebook','2026-10-07T12:00:00+03')",[id]);
 await event(db,"2026-10-07T12:00:02+03","navigation","human");
 await event(db,"2026-10-07T12:00:03+03","unverified","preview");
 const r=await readReport(db);assert.equal(r.rows[0].clicks,1);assert.equal(r.rows[0].unverified_clicks,0);
}));
test("SQL rolling interval ends at as-of rather than midnight",()=>sqlFixture(async db=>{
 await event(db,"2026-10-08T00:00:30+03","navigation");
 assert.equal((await readReport(db,false)).rows[0].clicks,1);
 assert.equal((await readReport(db,true)).rows.length,0);
}));
test("SQL report is inaccessible to anonymous and authenticated clients",()=>sqlFixture(async db=>{
 for(const role of ["anon","authenticated"]){
  await db.exec("set role "+role);
  await assert.rejects(db.query("select public.get_click_report_v2(1,true)"),/permission denied/);
  await db.exec("reset role");
 }
}));
