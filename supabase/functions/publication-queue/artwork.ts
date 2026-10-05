import { Resvg, initWasm } from 'npm:@resvg/resvg-wasm@2.6.2';
import {artworkSvg} from './layout.ts';
import {rasterType,assertVisibleProduct} from './image.ts';
let wasmReady:Promise<void>|null=null,fontsReady:Promise<Uint8Array[]>|null=null;
async function resource(url:string){
 const r=await fetch(url,{signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error('render-resource-unavailable');
 return new Uint8Array(await r.arrayBuffer());
}
async function fonts(){
 if(!wasmReady)wasmReady=resource('https://cdn.jsdelivr.net/npm/@resvg/resvg-wasm@2.6.2/index_bg.wasm').then(bytes=>initWasm(bytes)).catch(e=>{wasmReady=null;throw e;});
 await wasmReady;
 if(!fontsReady)fontsReady=Promise.all(['Regular','Bold'].map(weight=>resource('https://raw.githubusercontent.com/notofonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-'+weight+'.ttf'))).catch(e=>{fontsReady=null;throw e;});
 return fontsReady;
}
export async function artwork(d:any,image:Uint8Array,imageType:string,story=false){
 const type=rasterType(image);if(type==='image/webp'||type!==imageType)throw Error('image-format-not-renderable');
 const buffers=await fonts();
 let binary='';for(const byte of image)binary+=String.fromCharCode(byte);
 const picture='data:'+type+';base64,'+btoa(binary);
 const probe=new Resvg(`<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="64" height="64"><image width="64" height="64" preserveAspectRatio="xMidYMid meet" xlink:href="${picture}"/></svg>`);
 try{
  const product=probe.render();try{assertVisibleProduct(product.pixels);}finally{product.free();}
 }finally{probe.free();}
 const renderer=new Resvg(artworkSvg(d,picture,story),{font:{fontBuffers:buffers,defaultFontFamily:'Noto Sans'}});
 try{
  const rendered=renderer.render();try{return new Uint8Array(rendered.asPng());}finally{rendered.free();}
 }finally{renderer.free();}
}
