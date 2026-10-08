import { eligible, catalogueEligible, safeImage, validListingId, type Snapshot } from "./policy";
const SUPABASE_URL = (process.env.SUPABASE_URL || "https://cmexmobjpeavlppmffqi.supabase.co").replace(/\/$/, "");
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
export type Deal = {
 id: string; title: string; brand: string; price: number | null; competitorPrice: number | null;
 gapPercent: number | null; merchant: string; merchantSlug: string; competitorMerchant: string;
 imageUrl: string | null; href: string; checkedAt: string | null; manual: boolean; affiliate: boolean;
};
export async function snapshots(query: string): Promise<Snapshot[]> {
 if (!SERVICE_KEY) throw new Error("Website data connection unavailable");
 const r = await fetch(SUPABASE_URL + "/rest/v1/homepage_deals?" + query, {
  headers: { apikey: SERVICE_KEY, Authorization: "Bearer " + SERVICE_KEY },
  cache: "no-store", signal: AbortSignal.timeout(10000),
 });
 if (!r.ok) throw new Error("Website data unavailable");
 return r.json();
}
export async function getSnapshot(id: string): Promise<Snapshot | null> {
 if (!validListingId(id)) return null;
 const rows = await snapshots("select=*&id=eq." + encodeURIComponent(id) + "&limit=1");
 return rows[0] || null;
}
export async function getDeals(): Promise<Deal[]> {
 const cutoff = new Date(Date.now() - 3600000).toISOString();
 const [verified, discovery] = await Promise.all([
  snapshots("select=*&status=eq.verified&checked_at=gt." + encodeURIComponent(cutoff) + "&order=checked_at.desc&limit=90"),
  snapshots("select=*&status=eq.unverified&order=attempted_at.desc&limit=90"),
 ]);
 const rows=[...new Map([...verified.filter(row=>eligible(row)),...discovery.filter(row=>catalogueEligible(row))].map(row=>[String(row.offer_id || row.manual_id || row.id),row])).values()];
 return rows.map(row=>{
  const fresh=eligible(row),price=fresh?Number(row.price):null;
  const rival=fresh&&!row.manual_id?Number(row.competitor_price):null;
  return {
   id:String(row.id),title:String(row.title),brand:String(row.brand||""),price,
   competitorPrice:rival,gapPercent:price!==null&&rival?Math.round((rival-price)/rival*10000)/100:null,
   merchant:String(row.merchant_name),merchantSlug:String(row.merchant_slug),
   competitorMerchant:fresh?String(row.competitor_name||""):"",imageUrl:safeImage(row.image_url),
   href:(fresh?"/go/":"/urun/")+encodeURIComponent(String(row.id)),checkedAt:fresh?String(row.checked_at):null,
   manual:Boolean(row.manual_id),affiliate:Boolean(row.affiliate_url),
  };
 });
}
