import {xml,wrap,discountPresentation} from './core.ts';
const money=(n:number)=>new Intl.NumberFormat('tr-TR',{maximumFractionDigits:2}).format(n)+' TL';
export function discountLabel(gap:number){
 if(!Number.isFinite(gap)||gap<=0||gap>=100)throw Error('discount-invalid');
 return '%'+new Intl.NumberFormat('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:2}).format(gap);
}
export function artworkSvg(d:any,picture:string,story=false){
 const discount=discountPresentation(d);
 const h=story?1920:1350,offset=story?260:0;
 const title=wrap(String(d.title),42,3).map((line,i)=>`<text x="70" y="${850+offset+i*50}" font-size="37" font-weight="600">${xml(line)}</text>`).join('');
 const price=money(d.cheapest_price),priceSize=price.length>13?52:72;
 return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1080" height="${h}" viewBox="0 0 1080 ${h}">
 <rect width="1080" height="${h}" fill="#ffffff"/><g font-family="Noto Sans" fill="#0d3567">
 <rect width="1080" height="155" fill="#0d3567"/><text x="70" y="102" font-size="62" font-weight="700" fill="white">FİYATZADE</text>
 <text x="70" y="${220+offset}" font-size="36" font-weight="700" fill="#ff6f0c">GÜNCEL FIRSAT</text>
 <rect x="70" y="${255+offset}" width="940" height="510" rx="28" fill="#fff4e9"/>
 <image x="110" y="${270+offset}" width="860" height="480" preserveAspectRatio="xMidYMid meet" xlink:href="${xml(picture)}"/>
 ${title}
 <text x="70" y="${1030+offset}" font-size="32">${xml(d.merchant)}</text>
 <text x="70" y="${1080+offset}" font-size="24" fill="#667788">${xml(discount.comparisonLabel)}</text>
 <text x="70" y="${1125+offset}" font-size="34" text-decoration="line-through" fill="#667788">${xml(money(discount.comparisonPrice))}</text>
 <text x="70" y="${1170+offset}" font-size="24" fill="#ff6f0c" font-weight="700">FIRSAT FİYATI</text>
 <text x="70" y="${1250+offset}" font-size="${priceSize}" font-weight="700" fill="#ff6f0c">${xml(price)}</text>
 <g id="discount-badge">
 <rect x="585" y="${1020+offset}" width="425" height="220" rx="34" fill="#ff6f0c"/>
 <text x="797.5" y="${1065+offset}" text-anchor="middle" font-size="${discount.repeat?19:24}" font-weight="700" fill="white">${xml(discount.badgeTop)}</text>
 <text x="797.5" y="${1150+offset}" text-anchor="middle" font-size="86" font-weight="700" fill="white">${xml(discountLabel(discount.percent))}</text>
 <text x="797.5" y="${1200+offset}" text-anchor="middle" font-size="30" font-weight="700" fill="white">${xml(discount.badgeBottom)}</text></g>
 ${story?'<rect x="70" y="1675" width="940" height="110" rx="40" fill="#ff6f0c"/><text x="540" y="1744" text-anchor="middle" font-size="42" font-weight="700" fill="white">FIRSATI YAKALA</text>':''}
 <text x="70" y="${h-35}" font-size="22" fill="#667788">#işbirliği #reklam · Fiyat ve stok değişebilir.</text></g></svg>`;
}
