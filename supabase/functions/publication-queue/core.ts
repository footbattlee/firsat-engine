export const DOMAINS: Record<string,string> = {amazon:'amazon.com.tr',trendyol:'trendyol.com',hepsiburada:'hepsiburada.com',n11:'n11.com',mediamarkt:'mediamarkt.com.tr',vatan:'vatanbilgisayar.com'};
export function allowedUrl(raw:string,slug:string){
 try {const u=new URL(raw),d=DOMAINS[slug];return !!d&&u.protocol==='https:'&&!u.username&&!u.password&&(!u.port||u.port==='443')&&(u.hostname===d||u.hostname.endsWith('.'+d));}catch{return false;}
}
export function samePath(original:string,final:string,slug:string){
 const a=new URL(original).pathname.replace(/\/$/,'').toLowerCase(),b=new URL(final).pathname.replace(/\/$/,'').toLowerCase();
 if(a===b)return true;
 const ai=a.match(/-p-(\d+)(?:\/|$)/),bi=b.match(/-p-(\d+)(?:\/|$)/);
 return slug==='trendyol'&&!!ai&&!!bi&&ai[1]===bi[1];
}
export function products(value:any):any[]{
 if(Array.isArray(value))return value.flatMap(products);
 if(!value||typeof value!=='object')return [];
 const types=Array.isArray(value['@type'])?value['@type']:[value['@type']];
 return [...(types.some((t:string)=>['Product','ProductGroup'].includes(t))?[value]:[]),...products(value['@graph'])];
}
export function verifiedOffer(nodes:any[],slug:string){
 if(nodes.length!==1)throw Error('product-identity-ambiguous');
 const p=nodes[0];let offers=p.offers;offers=Array.isArray(offers)?offers:[offers];
 if(offers.length!==1||!offers[0])throw Error('multiple-offers-unverified');
 const o=offers[0],kind=o['@type'];
 if(kind!=='Offer'&&!(slug==='mediamarkt'&&kind==='AggregateOffer'))throw Error('offer-type-unverified');
 const condition=String(o.itemCondition||p.itemCondition||'').split('/').pop();
 if(condition&&condition!=='NewCondition')throw Error('used-product');
 if(/yenilenmiş|yenilenmis|teşhir|teshir|ikinci el|refurbished|outlet/iu.test(String(p.name)))throw Error('used-product');
 if(o.priceCurrency!=='TRY')throw Error('currency-unverified');
 const stock=String(o.availability||'').split('/').pop();
 if(stock!=='InStock')throw Error('stock-unverified');
 const price=Number(o.price??o.lowPrice);
 if(!Number.isFinite(price)||price<=0)throw Error('price-unverified');
 return {price,title:String(p.name||''),gtin:String(p.gtin13||p.gtin14||p.gtin||'')};
}
export function validateGap(price:number,competitor:number,candidate:any){
 if(!Number.isFinite(price)||!Number.isFinite(competitor)||price<=0||competitor<=price)throw Error('price-order-invalid');
 const gap=(competitor-price)/competitor*100;
 if(gap>=70||Number(candidate.history_drop_percent||0)>=60)throw Error('advantage-lost-or-suspicious');
 if(candidate.notification_reason==='redispatch_price_drop'){
  const previous=Number(candidate.previous_notified_price),drop=(previous-price)/previous*100;
  if(!Number.isFinite(previous)||previous<=price||drop+1e-9<15||drop>=60)throw Error('redispatch-drop-below-threshold-or-suspicious');
 }else if(gap<Number(candidate.threshold_percent||15))throw Error('advantage-lost-or-suspicious');
 return Math.round(gap*100)/100;
}
export function slotKey(now:Date){
 const local=new Date(now.getTime()+3*3600000),h=local.getUTCHours(),m=local.getUTCMinutes();
 if(h<10||h>23||m%30>=5)return null;
 local.setUTCMinutes(Math.floor(m/30)*30,0,0);return new Date(local.getTime()-3*3600000).toISOString();
}
export function xml(value:any){return String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');}
export function wrap(text:string,max=40,lines=3){
 const result:string[]=[];let line='';
 for(const word of text.split(/\s+/)){if((line+' '+word).trim().length>max&&line){result.push(line);line=word;}else line=(line+' '+word).trim();}
 if(line)result.push(line);if(result.length>lines){result.length=lines;result[lines-1]=result[lines-1].slice(0,max-3)+'...';}return result;
}
export function discountPresentation(d:any){
 const gap=validateGap(Number(d.cheapest_price),Number(d.competitor_price),d);
 if(d.notification_reason==='redispatch_price_drop'){
  const previous=Number(d.previous_notified_price);
  return {percent:Math.round((previous-Number(d.cheapest_price))/previous*10000)/100,
   comparisonPrice:previous,comparisonLabel:'ÖNCEKİ PAYLAŞIM',badgeTop:'SON PAYLAŞIMA GÖRE',badgeBottom:'FİYAT DÜŞTÜ',repeat:true};
 }
 return {percent:gap,comparisonPrice:Number(d.competitor_price),comparisonLabel:'RAKİP FİYAT',badgeTop:'RAKİPTEN',badgeBottom:'DAHA UCUZ',repeat:false};
}
