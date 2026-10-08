import {parseHTML} from "./web/node_modules/linkedom/esm/index.js";
import {allowedProduct,sameProduct,parsePrice} from "./supabase/functions/homepage-refresh/price.mjs";
let input="";for await(const chunk of process.stdin)input+=chunk;
try{
 const {html,url,finalUrl,slug}=JSON.parse(input);
 if(!allowedProduct(url,slug)||!sameProduct(url,finalUrl,slug))throw Error("product-redirect-unverified");
 const doc=parseHTML(html).document;for(const n of doc.querySelectorAll("style"))n.remove();
 process.stdout.write(JSON.stringify(parsePrice(doc,slug,finalUrl)));
}catch(e){process.stdout.write(JSON.stringify({error:e.message}));process.exitCode=1;}
