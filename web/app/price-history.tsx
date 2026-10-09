"use client";
import {useMemo,useState} from "react";
import type {HistoryPoint,StoreOffer} from "../lib/deals";
const money=new Intl.NumberFormat("tr-TR",{style:"currency",currency:"TRY"});
const date=(day:string)=>new Intl.DateTimeFormat("tr-TR",{day:"2-digit",month:"short",year:"numeric",timeZone:"Europe/Istanbul"}).format(new Date(day+"T12:00:00Z"));
export function PriceHistory({history,offers,defaultOffer}:{history:HistoryPoint[];offers:StoreOffer[];defaultOffer:string}) {
 const [selected,setSelected]=useState(history.some(h=>h.offer_id===defaultOffer)?defaultOffer:history[0]?.offer_id||"");
 const [days,setDays]=useState(90);
 const options=useMemo(()=>[...new Map(history.map(h=>[h.offer_id,h.merchant])).entries()],[history]);
 const points=useMemo(()=>{const cutoff=Date.now()-days*86400000;return history.filter(h=>h.offer_id===selected&&Date.parse(h.day+"T23:59:59+03:00")>=cutoff).sort((a,b)=>a.day.localeCompare(b.day));},[history,selected,days]);
 if(!history.length)return <section className="detailPanel"><h2>Fiyat geçmişi</h2><p>Bu ürün için henüz günlük fiyat kaydı yok. Sonraki aramalarda kaydedilen fiyatlar burada görünecek.</p></section>;
 const prices=points.map(p=>Number(p.price)),low=Math.min(...prices),high=Math.max(...prices);
 const padding=points.length?Math.max((high-low)*.15,high*.025,1):1,yMin=low-padding,yMax=high+padding;
 const left=125,right=735,top=25,bottom=235;
 const first=points.length?Date.parse(points[0].day):0,last=points.length?Date.parse(points.at(-1)!.day):1;
 const x=(day:string)=>last===first?(left+right)/2:left+(Date.parse(day)-first)/(last-first)*(right-left);
 const y=(price:number)=>bottom-(price-yMin)/(yMax-yMin)*(bottom-top);
 return <section className="detailPanel" id="fiyat-gecmisi"><div className="historyHead"><div><span className="eyebrow">GÜNLÜK ARAMA KAYITLARI</span><h2>Fiyat geçmişi</h2></div><div className="historyControls">
 <label>Mağaza teklifi<select aria-label="Fiyat geçmişi mağazası" value={selected} onChange={e=>setSelected(e.target.value)}>{options.map(([id,merchant])=><option value={id} key={id}>{merchant}{offers.find(o=>o.id===id)?.seller?" · "+offers.find(o=>o.id===id)?.seller:""}</option>)}</select></label>
 <label>Dönem<select aria-label="Fiyat geçmişi dönemi" value={days} onChange={e=>setDays(Number(e.target.value))}><option value={30}>Son 30 gün</option><option value={90}>Son 90 gün</option></select></label></div></div>
 <p className="detailMuted">Her teklif için günün son stokta fiyat kaydı gösterilir. Aranmayan günler doldurulmaz; yarım saatlik site kontrolleri bu grafiğe eklenmez.</p>
 {points.length?<><div className="historyStats"><span>Kaydedilen en düşük <b>{money.format(low)}</b></span><span>Son günlük kayıt <b>{money.format(Number(points.at(-1)!.price))}</b></span><span><b>{points.length}</b> kayıtlı gün</span></div>
 <div className="priceChart"><svg viewBox="0 0 760 285" role="img" aria-label={points.length+" günlük fiyat kaydı; en düşük "+money.format(low)}><title>Günlük fiyat geçmişi</title>
 {[0,.33,.66,1].map(f=><g key={f}><line x1={left} x2={right} y1={top+f*(bottom-top)} y2={top+f*(bottom-top)} stroke="#e4e9dd"/><text x={left-12} y={top+f*(bottom-top)+4} textAnchor="end" fill="#697766" fontSize="11">{money.format(yMax-f*(yMax-yMin))}</text></g>)}
 {points.map((p,i)=>i&&Date.parse(p.day)-Date.parse(points[i-1].day)===86400000?<line key={"line"+p.day} x1={x(points[i-1].day)} y1={y(Number(points[i-1].price))} x2={x(p.day)} y2={y(Number(p.price))} stroke="#6b872e" strokeWidth="3"/>:null)}
 {points.map(p=><circle key={p.day} cx={x(p.day)} cy={y(Number(p.price))} r="5" fill="#17352b"><title>{date(p.day)}: {money.format(Number(p.price))}</title></circle>)}
 {[...new Set([0,Math.floor((points.length-1)/2),points.length-1])].map(i=><text key={i} x={x(points[i].day)} y="264" textAnchor="middle" fill="#697766" fontSize="11">{date(points[i].day)}</text>)}
 </svg></div>
 <details className="historyTable"><summary>Tarih tarih fiyatları göster</summary><div className="tableScroll"><table><thead><tr><th>Tarih</th><th>Mağaza</th><th>Kaydedilen fiyat</th></tr></thead><tbody>{[...points].reverse().map(p=><tr key={p.day}><td><time dateTime={p.day}>{date(p.day)}</time></td><td>{p.merchant}</td><td>{money.format(Number(p.price))}</td></tr>)}</tbody></table></div></details></>:<p>Bu dönemde fiyat kaydı yok. Daha uzun bir dönem seçebilirsin.</p>}
 </section>;
}
