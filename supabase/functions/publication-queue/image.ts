const CDN_HOSTS=['dsmcdn.com','hepsiburada.net','media-amazon.com','ssl-images-amazon.com','n11scdn.akamaized.net','n11.com','vatanbilgisayar.com','mediamarkt.com.tr','mmst.eu','mmsrg.com'];
const MAX_BYTES=8*1024*1024;
export function productImageUrl(value:string){
 const u=new URL(value);
 if(u.protocol!=='https:'||u.username||u.password||(u.port&&u.port!=='443')||!CDN_HOSTS.some(h=>u.hostname===h||u.hostname.endsWith('.'+h)))throw Error('image-domain-unverified');
 // Hepsiburada's explicit WebP transformation overrides Accept negotiation.
 if(u.hostname.endsWith('.hepsiburada.net'))u.pathname=u.pathname.replace(/\/format:webp$/i,'');
 return u;
}
export function rasterType(bytes:Uint8Array){
 if(bytes.length>=8&&[137,80,78,71,13,10,26,10].every((v,i)=>bytes[i]===v))return 'image/png';
 if(bytes.length>=3&&bytes[0]===255&&bytes[1]===216&&bytes[2]===255)return 'image/jpeg';
 if(bytes.length>=12&&String.fromCharCode(...bytes.slice(0,4))==='RIFF'&&String.fromCharCode(...bytes.slice(8,12))==='WEBP')return 'image/webp';
 throw Error('image-content-invalid');
}
export async function fetchProductImage(value:string,fetcher:typeof fetch=fetch){
 let current=productImageUrl(value);
 for(let attempt=0;attempt<4;attempt++){
  const r=await fetcher(current,{redirect:'manual',headers:{Accept:'image/png,image/jpeg;q=0.9','User-Agent':'Mozilla/5.0','Referer':'https://www.google.com/'},signal:AbortSignal.timeout(12000)});
  if(r.status>=300&&r.status<400){
   const location=r.headers.get('location');if(!location)throw Error('image-redirect-invalid');
   current=productImageUrl(new URL(location,current).href);continue;
  }
  if(!r.ok)throw Error('image-unavailable');
  if(Number(r.headers.get('content-length')||0)>MAX_BYTES)throw Error('image-too-large');
  const bytes=new Uint8Array(await r.arrayBuffer());if(bytes.length>MAX_BYTES)throw Error('image-too-large');
  const type=rasterType(bytes);
  if(type==='image/webp')throw Error('image-format-not-renderable');
  return {bytes,type};
 }
 throw Error('image-redirect-limit');
}
export function assertVisibleProduct(pixels:Uint8Array){
 // Probe only the embedded product, on a transparent background. An unsupported
 // or corrupt image can otherwise disappear silently inside an otherwise valid PNG.
 let visible=0;
 for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>16&&(pixels[i]<248||pixels[i+1]<248||pixels[i+2]<248))visible++;
 if(visible<4)throw Error('product-image-not-visible');
}
