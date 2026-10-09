export const MAX_AGE_MS = 60 * 60 * 1000;
export type Snapshot = Record<string, unknown>;
const hosts: Record<string, string[]> = {
 amazon: ["amazon.com.tr", "amzn.to"],
 trendyol: ["trendyol.com", "ty.gl"],
 hepsiburada: ["hepsiburada.com", "hepsiburada.onelink.me", "app.hps.im", "hb.biz"],
 n11: ["n11.com"], mediamarkt: ["mediamarkt.com.tr"], vatan: ["vatanbilgisayar.com"],
};
export function safeDestination(raw: unknown, slug: unknown): string | null {
 try {
  const u = new URL(String(raw || ""));
  if (u.protocol !== "https:" || u.username || u.password || (u.port && u.port !== "443")) return null;
  return (hosts[String(slug)] || []).some(h => u.hostname === h || u.hostname.endsWith("." + h)) ? u.href : null;
 } catch { return null; }
}
export function safeImage(raw: unknown): string | null {
 try {
  const u = new URL(String(raw || ""));
  const domains = ["media-amazon.com", "ssl-images-amazon.com", "dsmcdn.com", "hepsiburada.net", "n11scdn.com", "n11scdn.akamaized.net", "assets.mmsrg.com", "mediamarkt.com", "mediamarkt.com.tr", "vatanbilgisayar.com"];
  return u.protocol === "https:" && !u.username && !u.password && domains.some(h => u.hostname === h || u.hostname.endsWith("." + h)) ? u.href : null;
 } catch { return null; }
}
export function eligible(row: Snapshot, now = Date.now()): boolean {
 const checked = Date.parse(String(row.checked_at || ""));
 const price = Number(row.price), rival = Number(row.competitor_price);
 const expiry = row.expires_at ? Date.parse(String(row.expires_at)) : Infinity;
 if (row.status !== "verified" || !Number.isFinite(checked) || checked > now + 5000 || now - checked >= MAX_AGE_MS || !(expiry > now)) return false;
 if (!Number.isFinite(price) || price <= 0 || !safeDestination(row.affiliate_url || row.product_url, row.merchant_slug)) return false;
 if (!row.manual_id) {
  const gap = (rival - price) / rival * 100;
  if (!Number.isFinite(gap) || gap < 15 || gap >= 70) return false;
 }
 return true;
}
export function validListingId(id: string): boolean {
 return /^(manual-)?[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id);
}

// A verified purchase price does not itself prove a competitor discount.
export function currentPriceEligible(row:Snapshot,now=Date.now()):boolean {
 const checked=Date.parse(String(row.price_checked_at||""));
 const expiry=row.expires_at?Date.parse(String(row.expires_at)):Infinity;
 return row.status!=="ended" && Number.isFinite(checked) && checked<=now+5000 && now-checked<MAX_AGE_MS
  && expiry>now && Number.isFinite(Number(row.price)) && Number(row.price)>0
  && !!String(row.title||"").trim() && !!safeDestination(row.affiliate_url||row.product_url,row.merchant_slug);
}
export function catalogueEligible(row: Snapshot, now = Date.now()): boolean {
 const attempted=Date.parse(String(row.attempted_at||""));
 const expiry=row.expires_at?Date.parse(String(row.expires_at)):Infinity;
 const reason=String(row.error_code||"");
 const temporary=/^(stock-unverified|purchase-price-unverified|stock-identity-unverified|page-schema-price-mismatch|store-http-403|store-http-429|store-http-5\d\d|check-failed)$/.test(reason)||/timeout|timed out|network|fetch failed/i.test(reason);
 return row.status==="unverified" && Number.isFinite(attempted) && attempted<=now+5000 && now-attempted<24*MAX_AGE_MS && expiry>now
  && temporary && !!String(row.title||"").trim() && !!safeDestination(row.affiliate_url||row.product_url,row.merchant_slug);
}

// Membership is supplied only by the private, approved-product catalogue RPC.
export function activeCatalogueEligible(row:Snapshot,now=Date.now()):boolean {
 const expiry=row.expires_at?Date.parse(String(row.expires_at)):Infinity;
 return row.catalogue_active===true && expiry>now && !!String(row.title||'').trim()
  && !!safeDestination(row.affiliate_url||row.product_url,row.merchant_slug);
}
