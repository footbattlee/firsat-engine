import test from "node:test";
import assert from "node:assert/strict";
import {brochureDate,safeBrochureUrl} from "../web/lib/brochure-parse.ts";
const now=new Date("2026-10-09T18:00:00Z");
test("official date ranges and upcoming catalogues are accepted, expired catalogues are hidden",()=>{assert.deepEqual(brochureDate("8 - 21 Ekim 2026",now),{start:"2026-10-08",end:"2026-10-21"});assert.deepEqual(brochureDate("11 Ekim Pazar",now),{start:"2026-10-11",end:null});assert.equal(brochureDate("24 Eylül - 7 Ekim 2026",now),null);assert.equal(brochureDate("1 - 5 Ekim 2026",now),null);assert.equal(brochureDate("31 Şubat 2026",now),null);assert.equal(brochureDate("16 Kasım 2026",now),null);});
test("brochures use only known official HTTPS sources",()=>{assert.equal(safeBrochureUrl("/Categories/680/afisler.aspx","https://www.bim.com.tr"),"https://www.bim.com.tr/Categories/680/afisler.aspx");for(const u of ["https://bim.com.tr.evil.example/a","javascript:alert(1)","http://www.bim.com.tr/a","https://user:pass@www.bim.com.tr/a"])assert.equal(safeBrochureUrl(u,"https://www.bim.com.tr"),null);});
