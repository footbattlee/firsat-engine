import { Resvg, initWasm } from 'npm:@resvg/resvg-wasm@2.6.2';
import {xml,wrap} from './core.ts';
let resources:Promise<Uint8Array>|null=null;
async function font(){
 if(!resources)resources=(async()=>{
  const wasm=await fetch('https://cdn.jsdelivr.net/npm/@resvg/resvg-wasm@2.6.2/index_bg.wasm');if(!wasm.ok)throw Error('wasm-resource-unavailable');
  await initWasm(await wasm.arrayBuffer());
  const f=await fetch('https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf');if(!f.ok)throw Error('font-resource-unavailable');
  return new Uint8Array(await f.arrayBuffer());
 })();return resources;
}
const money=(n:number)=>new Intl.NumberFormat('tr-TR',{maximumFractionDigits:2}).format(n)+' TL';
export async function artwork(d:any,image:Uint8Array,imageType:string,story=false){
 const fonts=await font(),h=story?1920:1350,offset=story?260:0;
 // Embedded bytes keep the renderer from making arbitrary network requests.
 let binary='';for(const byte of image)binary+=String.fromCharCode(byte);
 const picture='data:'+imageType+';base64,'+btoa(binary);
 const title=wrap(String(d.title),42,3).map((line,i)=>`<text x="70" y="${850+offset+i*50}" font-size="37" font-weight="600">${xml(line)}</text>`).join('');
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1080" height="${h}" viewBox="0 0 1080 ${h}">
 <rect width="1080" height="${h}" fill="#ffffff"/><g font-family="Noto Sans" fill="#0d3567">
 <rect x="0" y="0" width="1080" height="155" fill="#0d3567"/><text x="70" y="102" font-size="62" font-weight="700" fill="white">FİYATZADE</text>
 <text x="70" y="${220+offset}" font-size="36" font-weight="700" fill="#ff6f0c">GÜNCEL FIRSAT</text>
 <rect x="70" y="${255+offset}" width="940" height="510" rx="28" fill="#fff4e9"/>
 <image x="110" y="${270+offset}" width="860" height="480" preserveAspectRatio="xMidYMid meet" xlink:href="${picture}"/>
 ${title}<text x="70" y="${1022+offset}" font-size="32">${xml(d.merchant)}</text>
 <text x="70" y="${1090+offset}" font-size="32" fill="#667788">Rakip fiyat: ${xml(money(d.competitor_price))}</text>
 <text x="70" y="${1190+offset}" font-size="76" font-weight="700" fill="#ff6f0c">${xml(money(d.cheapest_price))}</text>
 <text x="70" y="${1250+offset}" font-size="32" font-weight="600">Rakipten %${xml(d.gap_percent)} daha ucuz</text>
 <text x="70" y="${h-35}" font-size="22" fill="#667788">#işbirliği #reklam · Fiyat ve stok değişebilir.</text></g></svg>`;
 const renderer=new Resvg(svg,{font:{fontBuffers:[fonts],defaultFontFamily:'Noto Sans'}});
 const rendered=renderer.render();const output=rendered.asPng();const copy=new Uint8Array(output);rendered.free();renderer.free();return copy;
}