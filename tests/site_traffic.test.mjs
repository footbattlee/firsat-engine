import test from "node:test";
import assert from "node:assert/strict";
import {trafficEvent,trafficKind} from "../web/lib/site-traffic.mjs";
import {formatClickReport} from "../supabase/functions/_shared/click-report.mjs";
const nav=new Headers({"user-agent":"Chrome/152","x-forwarded-for":"192.0.2.1","sec-fetch-mode":"navigate","sec-fetch-dest":"document","sec-fetch-user":"?1"});
test("site daily hash hides IP, rotates at Istanbul midnight and deduplicates repeats",()=>{
 const a=trafficEvent(nav,"outbound","/urun/a","secret",new Date("2026-10-08T20:59:59Z"));
 assert.deepEqual(a,trafficEvent(nav,"outbound","/urun/a","secret",new Date("2026-10-08T20:00:00Z")));
 const b=trafficEvent(nav,"outbound","/urun/a","secret",new Date("2026-10-08T21:00:00Z"));
 assert.notEqual(a.visitor_hash,b.visitor_hash);assert.notEqual(a.event_key,b.event_key);
 assert.doesNotMatch(JSON.stringify(a),/192\.0\.2\.1/);
});
test("site known bot, prefetch, unknown and visible client evidence remain separate",()=>{
 assert.equal(trafficKind(new Headers({"user-agent":"TelegramBot"}),"pageview"),"bot");
 assert.equal(trafficKind(new Headers({"user-agent":"Chrome","purpose":"prefetch"}),"outbound"),"prefetch");
 assert.equal(trafficKind(new Headers({"user-agent":"Chrome"}),"outbound"),"unverified");
 assert.equal(trafficKind(nav,"outbound"),"navigation");
 assert.equal(trafficKind(new Headers({"user-agent":"Chrome","sec-fetch-site":"same-origin","sec-fetch-mode":"same-origin","sec-fetch-dest":"empty"}),"pageview"),"client_view");
});
test("Telegram website counts do not inflate social link counts",()=>{
 const text=formatClickReport({period_start:"2026-10-08T21:00:00Z",period_end:"2026-10-09T21:00:00Z",rows:[{channel:"telegram",merchant:"Amazon",title:"Test",clicks:3}],website:{page_views:10,outbound_clicks:2,unverified_outbound:1}});
 assert.match(text,/Ana sayfa açılışı: <b>10/);assert.match(text,/Ana sayfadan mağazaya gidiş: <b>2/);
 assert.match(text,/Tarayıcı açılış sinyali olan: <b>3/);
 assert.ok(text.length<4096);
});
