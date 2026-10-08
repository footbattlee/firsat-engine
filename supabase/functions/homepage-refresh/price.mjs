export const STORES={amazon:'amazon.com.tr',trendyol:'trendyol.com',hepsiburada:'hepsiburada.com',n11:'n11.com',mediamarkt:'mediamarkt.com.tr',vatan:'vatanbilgisayar.com'};
export function allowedProduct(raw,slug){
 try{const u=new URL(raw),h=STORES[slug];return !!h&&u.protocol==='https:'&&!u.username&&!u.password&&(!u.port||u.port==='443')&&(u.hostname===h||u.hostname.endsWith('.'+h));}catch{return false;}
}
export function sameProduct(a,b,slug){
 if(!allowedProduct(b,slug))return false;
 const x=new URL(a),y=new URL(b);
 if(slug==='trendyol')return !!x.pathname.match(/-p-(\d+)/)&&x.pathname.match(/-p-(\d+)/)[1]===y.pathname.match(/-p-(\d+)/)?.[1]&&x.searchParams.get('merchantId')===y.searchParams.get('merchantId');
 return x.pathname.replace(/\/$/,'').toLowerCase()===y.pathname.replace(/\/$/,'').toLowerCase();
}
export function amount(raw){
 let s=String(raw||'').replace(/[^\d.,]/g,'');if(!s)return null;
 const c=s.lastIndexOf(','),d=s.lastIndexOf('.');
 const dec=c>=0&&d>=0?(c>d?',':'.'):c>=0&&s.length-c<=3?',':d>=0&&s.length-d<=3?'.':null;
 s=dec?s.replace(dec===','?/\./g:/,/g,'').replace(dec,'.'):s.replace(/[.,]/g,'');
 const n=Number(s);return Number.isFinite(n)&&n>0?n:null;
}
export function productNodes(v){
 if(Array.isArray(v))return v.flatMap(productNodes);
 if(!v||typeof v!=='object')return [];
 const types=Array.isArray(v['@type'])?v['@type']:[v['@type']];
 return [...(types.some(x=>['Product','ProductGroup'].includes(x))?[v]:[]),...productNodes(v['@graph'])];
}
// JSON-LD alone can lag behind the visitor's purchase price.
export function parsePrice(doc,slug,url){
 const title=doc.querySelector('h1,#productTitle')?.textContent?.trim();
 if(!title||/yenilenmi[sş]|ikinci el|refurbished|te[sş]hir/iu.test(title))throw Error('product-identity-unverified');
 let price=null;
 if(slug==='amazon'){
  const asin=new URL(url).pathname.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})/i)?.[1];
  if(!asin||doc.querySelector('input#ASIN')?.getAttribute('value')!==asin)throw Error('product-identity-unverified');
  const stock=doc.querySelector('#availability')?.textContent?.toLowerCase()||'';
  if(!stock.includes('stokta')||/yok|değil|degil|tükendi/u.test(stock))throw Error('stock-unverified');
  const minimum=doc.querySelector('#quantity option[value]:not([value=""])')?.getAttribute('value');
  if(minimum&&Number(minimum)>1)throw Error('minimum-quantity-condition');
  if(!doc.querySelector('#add-to-cart-button')||doc.querySelector('#add-to-cart-button')?.hasAttribute('disabled'))throw Error('purchase-unavailable');
  price=amount(doc.querySelector('#corePrice_feature_div .a-price:not(.a-text-price) .a-offscreen,#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-price) .a-offscreen')?.textContent);
 }else{
  const selectors={trendyol:"[data-testid='price-value'],.prc-box-sllng,.prc-box-dscntd",hepsiburada:"[data-test-id='price-current-price'],#offering-price,.price-text",n11:'.newPrice ins,.newPrice',mediamarkt:"[data-test='branded-price-whole-value']",vatan:'.product-list__price'};
  const prices=[...doc.querySelectorAll(selectors[slug]||'')].filter(n=>!n.closest('del,s,[class*=coupon],[class*=plus],[class*=installment]')).map(n=>amount(n.textContent)).filter(Boolean);
  const unique=[...new Set(prices)];if(unique.length!==1)throw Error('purchase-price-unverified');price=unique[0];
  const schemas=[...doc.querySelectorAll('script[type="application/ld+json"]')].flatMap(n=>{try{return productNodes(JSON.parse(n.textContent));}catch{return [];}});
  if(schemas.length!==1)throw Error('stock-identity-unverified');
  const offers=Array.isArray(schemas[0].offers)?schemas[0].offers:[schemas[0].offers];
  if(offers.length!==1||!offers[0]||offers[0].priceCurrency!=='TRY'||!String(offers[0].availability).endsWith('/InStock'))throw Error('stock-unverified');
  const sp=Number(offers[0].price??offers[0].lowPrice);
  if(!Number.isFinite(sp)||Math.abs(sp-price)>0.02)throw Error('page-schema-price-mismatch');
 }
 if(!price)throw Error('purchase-price-unverified');return {price,title};
}
export function advantage(price,rival){const g=(rival-price)/rival*100;return Number.isFinite(g)&&g>=15&&g<70?Math.round(g*100)/100:null;}
