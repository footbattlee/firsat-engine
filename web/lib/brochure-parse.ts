export const BROCHURE_STORES=[
 {id:"bim",name:"BİM",url:"https://www.bim.com.tr/Categories/680/afisler.aspx",description:"Aktüel ürünler ve indirim afişleri",color:"#db2737"},
 {id:"a101",name:"A101",url:"https://www.a101.com.tr/afisler",description:"Aldın Aldın ve Haftanın Yıldızları",color:"#009bbb"},
 {id:"sok",name:"ŞOK",url:"https://kurumsal.sokmarket.com.tr/tr/firsatlar",description:"Haftanın ve hafta sonunun fırsatları",color:"#e4ba20"},
 {id:"migros",name:"Migros",url:"https://www.money.com.tr/migroskop-dijital",description:"Migroskop dijital katalog",color:"#f07820"}
] as const;
export type Brochure={store:string;name:string;title:string;href:string;dateLabel:string;start:string|null;end:string|null;image:string|null;color:string;sourceUrl:string};
const months=["ocak","subat","mart","nisan","mayis","haziran","temmuz","agustos","eylul","ekim","kasim","aralik"];
const norm=(s:string)=>s.toLocaleLowerCase("tr").replace(/ı/g,"i").normalize("NFD").replace(/[\u0300-\u036f]/g,"");
export function brochureDate(label:string,now=new Date()){
 const text=norm(label),month=months.findIndex(m=>new RegExp("\\b"+m+"\\b").test(text));
 if(month<0)return null;
 const yearMatch=text.match(/\b(20\d{2})\b/);
 const dayMatches=text.split(months[month])[0].match(/\d{1,2}/g);if(!dayMatches?.length)return null;
 const days=dayMatches.slice(-2).map(Number),year=yearMatch?Number(yearMatch[1]):now.getUTCFullYear();
 const startDay=days[0],endDay=days.at(-1)!;
 if(startDay<1||endDay>31||startDay>endDay)return null;
 let start=new Date(Date.UTC(year,month,startDay)),end=new Date(Date.UTC(year,month,endDay));
 if(start.getUTCMonth()!==month||end.getUTCMonth()!==month)return null;
 if(!yearMatch){if(start.getTime()-now.getTime()>180*86400000){start.setUTCFullYear(year-1);end.setUTCFullYear(year-1);}else if(now.getTime()-end.getTime()>180*86400000){start.setUTCFullYear(year+1);end.setUTCFullYear(year+1);}}
 const today=new Date(now.toLocaleDateString("en-CA",{timeZone:"Europe/Istanbul"})+"T00:00:00Z");
 if(days.length>1?end<today:start.getTime()<today.getTime()-6*86400000)return null;
 if(start.getTime()>today.getTime()+14*86400000)return null;
 return {start:start.toISOString().slice(0,10),end:days.length>1?end.toISOString().slice(0,10):null};
}
export function safeBrochureUrl(raw:string,base:string){
 try{const u=new URL(raw,base);const allowed=["bim.com.tr","a101.com.tr","sokmarket.com.tr","ceptesok.com","money.com.tr","moneyclubkart.azureedge.net"];
 return u.protocol==="https:"&&!u.username&&!u.password&&(!u.port||u.port==="443")&&allowed.some(h=>u.hostname===h||u.hostname.endsWith("."+h))?u.href:null;}catch{return null;}
}
