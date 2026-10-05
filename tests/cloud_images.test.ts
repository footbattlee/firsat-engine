import test from 'node:test';
import assert from 'node:assert/strict';
import {productImageUrl,rasterType,fetchProductImage,assertVisibleProduct} from '../supabase/functions/publication-queue/image.ts';
import {artworkSvg,discountLabel} from '../supabase/functions/publication-queue/layout.ts';
const jpeg=Uint8Array.of(255,216,255,224);
test('CDN images request JPEG/PNG and remove explicit Hepsiburada WebP transform',async()=>{
 let target='',headers:any;
 const fake=async(url:any,options:any)=>{target=String(url);headers=options.headers;return new Response(jpeg,{headers:{'content-type':'image/webp'}});};
 const photo=await fetchProductImage('https://productimages.hepsiburada.net/s/777/375/110002264690858.jpg/format:webp',fake as typeof fetch);
 assert.equal(target,'https://productimages.hepsiburada.net/s/777/375/110002264690858.jpg');
 assert.ok(!headers.Accept.includes('webp'));
 assert.equal(photo.type,'image/jpeg'); // Trust decoded signature over extension/header.
});
test('unsupported WebP, HTML and redirects outside known CDNs stop preparation',async()=>{
 const webp=new TextEncoder().encode('RIFF1234WEBPpayload');
 assert.equal(rasterType(webp),'image/webp');
 await assert.rejects(fetchProductImage('https://cdn.dsmcdn.com/x.jpg',async()=>new Response(webp)),/image-format-not-renderable/);
 await assert.rejects(fetchProductImage('https://cdn.dsmcdn.com/x.jpg',async()=>new Response('<html>error</html>')),/image-content-invalid/);
 await assert.rejects(fetchProductImage('https://cdn.dsmcdn.com/x.jpg',async()=>new Response(null,{status:302,headers:{location:'https://example.org/x.jpg'}})),/image-domain-unverified/);
 for(const u of ['http://cdn.dsmcdn.com/x.jpg','https://cdn.dsmcdn.com.evil.example/x.jpg','https://x:pw@cdn.dsmcdn.com/x.jpg'])assert.throws(()=>productImageUrl(u));
});
test('transparent or blank product probes cannot be published',()=>{
 assert.throws(()=>assertVisibleProduct(new Uint8Array(64*64*4)),/product-image-not-visible/);
 assert.throws(()=>assertVisibleProduct(new Uint8Array(64*64*4).fill(255)),/product-image-not-visible/);
 const visible=new Uint8Array(16);for(let i=0;i<16;i+=4)visible[i+3]=255;
 assert.doesNotThrow(()=>assertVisibleProduct(visible));
});
test('discount is emphasized in Turkish notation on post and story without overlapping prices',()=>{
 assert.equal(discountLabel(25.74),'%25,74');
 const d={title:'Product <script>',merchant:'Store',cheapest_price:11139,competitor_price:14999,gap_percent:25.74};
 const post=artworkSvg(d,'data:image/png;base64,test'),story=artworkSvg(d,'data:image/png;base64,test',true);
 assert.ok(post.includes('%25,74'));assert.ok(post.includes('DAHA UCUZ'));
 assert.ok(post.includes('x="585" y="1020" width="425" height="220"'));
 assert.ok(story.includes('x="585" y="1280" width="425" height="220"'));
 assert.ok(post.includes('Product &lt;script&gt;'));assert.ok(!post.includes('<script>'));
 for(const v of [0,NaN,Infinity,100])assert.throws(()=>discountLabel(v));
});

test('repeat artwork emphasizes actual old-price drop even when competitor gap also qualifies',()=>{
 const svg=artworkSvg({title:'Termos',merchant:'Store',cheapest_price:2199,competitor_price:2799,
  gap_percent:21.44,notification_reason:'redispatch_price_drop',previous_notified_price:2699},'data:image/png;base64,test');
 assert.ok(svg.includes('%18,53'));assert.ok(!svg.includes('%21,44'));
 assert.ok(svg.includes('2.699 TL'));assert.ok(!svg.includes('2.799 TL'));
 assert.ok(svg.includes('SON PAYLA\u015eIMA G\u00d6RE'));
});
