const SUPABASE_URL = (process.env.SUPABASE_URL || "https://cmexmobjpeavlppmffqi.supabase.co").replace(/\/$/, "");
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "";

type Row = Record<string, unknown>;

export type Deal = {
  id: string;
  title: string;
  brand: string;
  price: number;
  competitorPrice: number;
  gapPercent: number;
  historyDropPercent: number;
  verified: boolean;
  merchant: string;
  competitorMerchant: string;
  productUrl: string;
  updatedAt: string;
};

async function sb(table: string, query: string): Promise<Row[]> {
  if (!SERVICE_KEY) throw new Error("SUPABASE_SERVICE_ROLE_KEY is not configured");
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${table}?${query}`, {
    headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` },
    next: { revalidate: 300 },
  });
  if (!response.ok) throw new Error(`Supabase ${table}: ${response.status}`);
  return response.json();
}

export async function getDeals(): Promise<Deal[]> {
  const candidates = await sb("deal_candidates", "select=*&status=eq.candidate&order=gap_percent.desc&limit=60");
  if (!candidates.length) return [];

  const canonicalIds = [...new Set(candidates.map(x => String(x.canonical_product_id)))];
  const offerIds = [...new Set(candidates.map(x => String(x.cheapest_offer_id)))];
  const merchantIds = [...new Set(candidates.flatMap(x => [String(x.cheapest_merchant_id), String(x.competitor_merchant_id)]))];

  const [products, offers, merchants] = await Promise.all([
    sb("canonical_products", `select=id,title,brand&id=in.(${canonicalIds.join(",")})`),
    sb("offers", `select=id,product_url&id=in.(${offerIds.join(",")})`),
    sb("merchants", `select=id,name,slug&id=in.(${merchantIds.join(",")})`),
  ]);

  const productMap = new Map(products.map(x => [String(x.id), x]));
  const offerMap = new Map(offers.map(x => [String(x.id), x]));
  const merchantMap = new Map(merchants.map(x => [String(x.id), String(x.name || x.slug || "Mağaza")]));

  return candidates.map(x => {
    const product = productMap.get(String(x.canonical_product_id)) || {};
    const offer = offerMap.get(String(x.cheapest_offer_id)) || {};
    return {
      id: String(x.id),
      title: String(product.title || "Ürün"),
      brand: String(product.brand || ""),
      price: Number(x.cheapest_price || 0),
      competitorPrice: Number(x.competitor_price || 0),
      gapPercent: Number(x.gap_percent || 0),
      historyDropPercent: Number(x.history_drop_percent || 0),
      verified: Boolean(x.verified),
      merchant: merchantMap.get(String(x.cheapest_merchant_id)) || "Mağaza",
      competitorMerchant: merchantMap.get(String(x.competitor_merchant_id)) || "Rakip mağaza",
      productUrl: String(offer.product_url || "#"),
      updatedAt: String(x.updated_at || ""),
    };
  });
}
