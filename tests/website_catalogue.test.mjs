import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import {join} from "node:path";
import {categoryFor} from "../web/lib/categories.ts";
import {activeCatalogueEligible,currentPriceEligible} from "../web/lib/policy.ts";
test("category shortcuts distinguish vitamins from electronics and school from cleaning",()=>{
 for(const [title,expected] of [["Redoxon Üçlü Etki 30 Efervesan Tablet","saglik"],["Huawei FreeBuds SE 4 ANC","elektronik"],["Stanley AeroLight Termos","ev-mutfak"],["M5 Kablosuz Göğüs Pompası","anne-bebek"],["Bouncy Blush Allık","kozmetik-bakim"],["C Vitaminli Fondöten","kozmetik-bakim"],["Power Bank 10000MAH","elektronik"],["Türkiye Atlası","kitap-okul"],["Fotokopi Kağıdı 500 Adet","kitap-okul"]])
 assert.equal(categoryFor(title),expected);
});
test("an active catalogue link never turns a stale stored price into a current price",()=>{
 const row={catalogue_active:true,title:"Product",status:"pending",price:400,product_url:"https://www.amazon.com.tr/dp/B08S7QYCKQ",merchant_slug:"amazon"};
 assert.equal(activeCatalogueEligible(row),true);assert.equal(currentPriceEligible(row),false);
 assert.equal(activeCatalogueEligible({...row,catalogue_active:false}),false);
 assert.equal(activeCatalogueEligible({...row,product_url:"https://evil.example"}),false);
 assert.equal(activeCatalogueEligible({...row,expires_at:"2000-01-01"}),false);
});
const require=createRequire(join(process.env.QUEUE_SQL_TEST_RUNTIME,"package.json"));
const {PGlite}=require("@electric-sql/pglite");
const ids=Array.from({length:9},(_,i)=>"00000000-0000-4000-8000-"+String(i+1).padStart(12,"0"));
test("private catalogue has no 60 cap; daily history and comparison respect offer identity",async()=>{
 const db=new PGlite();try{
 await db.exec(`
 create role anon;create role authenticated;create role service_role;
 create table canonical_products(id uuid primary key,title text,brand text,active bool);
 create table categories(id uuid primary key,slug text,name text);
 create table merchants(id uuid primary key,slug text,name text,active bool);
 create table products(id uuid primary key,category_id uuid,active bool);
 create table product_variants(id uuid primary key,product_id uuid,active bool,gtin text,color text,size text,capacity text);
 create table offers(id uuid primary key,product_variant_id uuid,merchant_id uuid,product_url text,affiliate_url text,image_url text,currency text,price numeric,in_stock bool,seller_name text,last_checked_at timestamptz);
 create table product_matches(canonical_product_id uuid,product_id uuid,status text);
 create table deal_candidates(id uuid primary key,canonical_product_id uuid,cheapest_offer_id uuid,competitor_offer_id uuid,status text,detected_at timestamptz);
 create table homepage_manual_deals(id uuid,title text,brand text,product_url text,affiliate_url text,image_url text,merchant_slug text,active bool,expires_at timestamptz);
 create table homepage_deals(id text,offer_id uuid,status text,title text,image_url text,price numeric,competitor_price numeric,competitor_name text,checked_at timestamptz,price_checked_at timestamptz,attempted_at timestamptz,error_code text);
 create table price_history(id bigint generated always as identity,offer_id uuid,price numeric,in_stock bool,checked_at timestamptz);
 `);
 await db.query("insert into canonical_products values($1,'Product','Brand',true)",[ids[0]]);
 await db.query("insert into merchants values($1,'amazon','Amazon',true),($2,'n11','n11',true)",[ids[1],ids[2]]);
 await db.query("insert into products values($1,null,true),($2,null,true)",[ids[3],ids[4]]);
 await db.query("insert into product_variants values($1,$2,true,'123',null,null,null),($3,$4,true,'123',null,null,null),($5,$4,true,'999',null,null,null)",[ids[5],ids[3],ids[6],ids[4],ids[7]]);
 await db.query("insert into offers values($1,$2,$3,'https://www.amazon.com.tr/dp/B08S7QYCKQ','https://www.amazon.com.tr/dp/B08S7QYCKQ?tag=owner-21',null,'TRY',400,true,null,now()),($4,$5,$6,'https://www.n11.com/urun/test',null,null,'TRY',600,true,null,now()),($7,$8,$6,'https://www.n11.com/urun/wrong',null,null,'TRY',50,true,null,now())",[ids[5],ids[5],ids[1],ids[6],ids[6],ids[2],ids[7],ids[7]]);
 await db.query("insert into product_matches values($1,$2,'approved'),($1,$3,'approved')",[ids[0],ids[3],ids[4]]);
 for(let i=0;i<101;i++)await db.query("insert into deal_candidates values($1,$2,$3,$4,'candidate',now())",["10000000-0000-4000-8000-"+String(i).padStart(12,"0"),ids[0],ids[5],ids[6]]);
 await db.query("insert into price_history(offer_id,price,in_stock,checked_at) values($1,410,true,date_trunc('day',now())-interval '1 day'+interval '10 hours'),($1,400,true,date_trunc('day',now())-interval '1 day'+interval '11 hours'),($1,1,false,date_trunc('day',now())-interval '1 day'+interval '12 hours'),($2,10,true,now()-interval '1 day')",[ids[5],ids[7]]);
 await db.exec(readFileSync(new URL("../supabase/website_catalogue.sql",import.meta.url),"utf8"));
 const listing="10000000-0000-4000-8000-000000000000";
 assert.equal((await db.query("select count(*)::int n from website_catalogue()")).rows[0].n,101);
 const offers=(await db.query("select x from website_product_offers($1) x",[listing])).rows.map(r=>r.x);
 assert.equal(offers.length,2);assert.ok(!offers.some(o=>o.id===ids[7]));assert.match(offers.find(o=>o.id===ids[5]).affiliate_url,/tag=owner-21/);
 const history=(await db.query("select x from website_price_history($1) x",[listing])).rows.map(r=>r.x);
 assert.equal(history.length,1);assert.equal(history[0].price,400);assert.equal(history[0].offer_id,ids[5]);
 assert.equal((await db.query("select count(*)::int n from website_catalogue('not-a-listing')")).rows[0].n,0);
 for(const name of ["website_catalogue","website_product_offers","website_price_history"]){
 const result=await db.query("select has_function_privilege('anon',$1,'execute') anon,has_function_privilege('service_role',$1,'execute') service",[name+"(text)"]);
 assert.equal(result.rows[0].anon,false);assert.equal(result.rows[0].service,true);
 }
 }finally{await db.close();}
});
