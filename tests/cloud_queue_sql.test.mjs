
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {join} from 'node:path';
// Install @electric-sql/pglite in a disposable directory and set QUEUE_SQL_TEST_RUNTIME.
// This executes the production SQL in isolated PostgreSQL, without network access.
const require=createRequire(join(process.env.QUEUE_SQL_TEST_RUNTIME,'package.json'));
const {PGlite}=require('@electric-sql/pglite');
const schema=`
create role anon;create role authenticated;create role service_role;
create table public.deal_candidates(id uuid primary key,canonical_product_id uuid unique,status text,scan_started_at timestamptz,notification_reason text,previous_notified_price numeric,redispatch_drop_percent numeric,cheapest_price numeric);
create table public.deal_approval_dispatches(deal_candidate_id uuid primary key,status text,sent_at timestamptz,created_at timestamptz default now());
create table public.deal_publications(deal_candidate_id uuid,platform text,status text,updated_at timestamptz,primary key(deal_candidate_id,platform));
create table public.publication_queue_settings(id boolean primary key,enabled boolean,not_before timestamptz,source_after timestamptz);
create table public.publication_scan_batches(started_at timestamptz primary key,completed_at timestamptz);
create table public.publication_queue(candidate_id uuid primary key,canonical_product_id uuid unique,state text default 'queued',
 enqueued_at timestamptz default now(),next_check_at timestamptz default now(),updated_at timestamptz default now(),
 claim_token uuid,snapshot jsonb,last_error text,source_run_started_at timestamptz,notification_context jsonb);
create table public.publication_slots(slot_at timestamptz primary key,candidate_id uuid);
insert into public.publication_queue_settings values(true,true,null,'2026-10-01T00:00:00Z');
insert into public.publication_scan_batches values('2026-10-04T17:53:03Z',now()),('2026-10-05T07:00:00Z',now()),('2026-10-06T07:00:00Z',null);
`;
const id='00000000-0000-0000-0000-000000000001';
const old='2026-10-04T17:53:03Z', later='2026-10-05T07:00:00Z';
async function fixture(fn){
 const db=new PGlite();try{
  await db.exec(schema);
  await db.exec(readFileSync(new URL('../supabase/publication_queue_admin_scope.sql',import.meta.url),'utf8'));
  await db.exec('create trigger enqueue_publication_candidate after insert or update on public.deal_candidates for each row execute function public.queue_deal_candidate()');
  await db.query('insert into public.deal_candidates(id,canonical_product_id,status,scan_started_at) values($1,$1,$2,$3)',[id,'candidate',old]);
  await fn(db);
 }finally{await db.close();}
}
async function sent(db,time=old){await db.query("insert into public.deal_approval_dispatches(deal_candidate_id,status,sent_at) values($1,'sent',$2)",[id,time]);}
async function eligible(db){return (await db.query('select public.publication_candidate_is_eligible($1) as ok',[id])).rows[0].ok;}
async function queue(db){return (await db.query('select * from public.publication_queue')).rows;}

test('candidate refresh without a new admin notification never enqueues',()=>fixture(async db=>{
 await sent(db,'2026-10-03T12:00:00Z');
 await db.query('update public.deal_candidates set scan_started_at=$1',[later]);
 assert.equal((await queue(db)).length,0);
}));
test('a successful new admin notification enqueues and qualifies',()=>fixture(async db=>{
 await sent(db);assert.equal((await queue(db)).length,1);assert.equal(await eligible(db),true);
}));
test('failed admin send does not enqueue; retry success does',()=>fixture(async db=>{
 await db.query("insert into public.deal_approval_dispatches(deal_candidate_id,status,sent_at) values($1,'failed',null)",[id]);
 assert.equal((await queue(db)).length,0);
 await db.query("update public.deal_approval_dispatches set status='sent',sent_at=$1",[old]);
 assert.equal(await eligible(db),true);
}));
test('new pending item survives later price refresh with its original queue position',()=>fixture(async db=>{
 await sent(db);const before=(await queue(db))[0];
 await db.query('update public.deal_candidates set scan_started_at=$1',[later]);
 const after=(await queue(db))[0];
 assert.equal(after.source_run_started_at.toISOString(),before.source_run_started_at.toISOString());
 assert.equal(after.enqueued_at.toISOString(),before.enqueued_at.toISOString());
 assert.equal(await eligible(db),true);
}));
test('pending item waits for the latest scan to finish',()=>fixture(async db=>{
 await sent(db);
 await db.query('update public.deal_candidates set scan_started_at=$1',['2026-10-06T07:00:00Z']);
 assert.equal(await eligible(db),false);
 await db.query("update public.publication_scan_batches set completed_at=now() where started_at='2026-10-06T07:00:00Z'");
 assert.equal(await eligible(db),true);
}));
test('old notification cannot qualify an existing wrongly requeued item',()=>fixture(async db=>{
 await sent(db,'2026-10-03T12:00:00Z');
 await db.query('insert into public.publication_queue(candidate_id,canonical_product_id,source_run_started_at) values($1,$1,$2)',[id,old]);
 assert.equal(await eligible(db),false);
 await db.exec('insert into public.publication_slots values(now(),null)');
 assert.equal((await db.query('select * from public.claim_publication_item((select slot_at from public.publication_slots))')).rows.length,0);
}));
test('old notification cannot bypass begin guard with a fabricated claim',()=>fixture(async db=>{
 await sent(db,'2026-10-03T12:00:00Z');
 await db.query("insert into public.publication_queue(candidate_id,canonical_product_id,source_run_started_at,state,claim_token) values($1,$1,$2,'checking',$1)",[id,old]);
 await db.exec('insert into public.publication_slots values(now(),null)');
 assert.equal((await db.query("select public.begin_publication($1,$1,(select slot_at from public.publication_slots),'{}') as ok",[id])).rows[0].ok,false);
 assert.equal((await db.query('select * from public.deal_publications')).rows.length,0);
}));
test('new notification restores excluded held item but never ambiguous held item',()=>fixture(async db=>{
 await db.query("insert into public.publication_queue(candidate_id,canonical_product_id,source_run_started_at,state,last_error) values($1,$1,$2,'held','Excluded: previous admin notification')",[id,old]);
 await sent(db);assert.equal((await queue(db))[0].state,'queued');
 await db.exec("update public.publication_queue set state='held',last_error='Instagram outcome requires review'");
 await db.query('update public.deal_candidates set scan_started_at=$1',[later]);
 await db.query('update public.deal_approval_dispatches set sent_at=$1',[later]);
 assert.equal((await queue(db))[0].state,'held');
}));
test('known published and ambiguous failed Instagram records never qualify',()=>fixture(async db=>{
 await sent(db);
 for(const state of ['published','publishing','failed']){
  await db.query("insert into public.deal_publications values($1,'instagram',$2,now()) on conflict(deal_candidate_id,platform) do update set status=excluded.status",[id,state]);
  assert.equal(await eligible(db),false);
 }
}));
test('valid new item can claim and reserve once; disabled queue cannot claim',()=>fixture(async db=>{
 await sent(db);await db.exec('insert into public.publication_slots values(now(),null)');
 await db.exec('update public.publication_queue_settings set enabled=false');
 assert.equal((await db.query('select * from public.claim_publication_item((select slot_at from public.publication_slots))')).rows.length,0);
 await db.exec('update public.publication_queue_settings set enabled=true');
 const q=(await db.query('select * from public.claim_publication_item((select slot_at from public.publication_slots))')).rows[0];assert.equal(q.candidate_id,id);
 assert.equal((await db.query("select public.begin_publication($1,$2,(select slot_at from public.publication_slots),'{}') as ok",[id,q.claim_token])).rows[0].ok,true);
 assert.equal((await db.query("select public.begin_publication($1,$2,(select slot_at from public.publication_slots),'{}') as ok",[id,q.claim_token])).rows[0].ok,false);
}));

test('repeat publication below 15 percent cannot claim even with a qualifying competitor gap',()=>fixture(async db=>{
 await db.query("update public.deal_candidates set notification_reason='redispatch_price_drop',previous_notified_price=1000,cheapest_price=851");
 await sent(db);assert.equal(await eligible(db),false);
 await db.query("update public.deal_candidates set cheapest_price=850");
 assert.equal(await eligible(db),true);
}));
test('repeat notification context survives later metadata refresh',()=>fixture(async db=>{
 await db.query("update public.deal_candidates set notification_reason='redispatch_price_drop',previous_notified_price=1000,cheapest_price=850");
 await sent(db);
 await db.query("update public.deal_candidates set notification_reason='competitor_gap',previous_notified_price=null,scan_started_at=$1",[later]);
 assert.equal((await queue(db))[0].notification_context.previous_notified_price,1000);
 assert.equal(await eligible(db),true);
 await db.query("update public.deal_candidates set cheapest_price=900");
 assert.equal(await eligible(db),false);
}));

test('legacy repeat without original price context stays excluded',()=>fixture(async db=>{
 await sent(db);
 await db.query("update public.deal_approval_dispatches set created_at='2026-10-03T00:00:00Z'");
 await db.query("update public.publication_queue set notification_context=null");
 assert.equal(await eligible(db),false);
}));
