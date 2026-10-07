import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";
import { requestMetadata } from "../_shared/click-request.mjs";

const env = (name: string) => Deno.env.get(name)?.trim() || "";
const sbUrl = env("SUPABASE_URL");
const service = env("SUPABASE_SERVICE_ROLE_KEY") || (() => {
  try { return JSON.parse(env("SUPABASE_SECRET_KEYS")).default || ""; }
  catch { return ""; }
})();
const sb = createClient(sbUrl, service);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const CHANNELS = new Set(["telegram", "facebook", "instagram", "story", "whatsapp", "other"]);

async function visitorHash(req: Request, deal: string, userAgent: string) {
  const ip = (req.headers.get("cf-connecting-ip") || req.headers.get("x-forwarded-for") || "").split(",")[0].trim();
  const localDay = new Intl.DateTimeFormat("en-CA", {timeZone: "Europe/Istanbul"}).format(new Date());
  const bytes = new TextEncoder().encode(`${localDay}|${deal}|${ip}|${userAgent}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function plain(message: string, status = 400) {
  return new Response(message, {
    status,
    headers: {"content-type": "text/plain; charset=utf-8", "cache-control": "no-store"},
  });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "GET" && req.method !== "HEAD") return plain("method not allowed", 405);

  const url = new URL(req.url);
  const deal = url.searchParams.get("deal") || "";
  const offerId = url.searchParams.get("offer") || "";
  const rawChannel = (url.searchParams.get("channel") || "other").toLowerCase();
  const channel = CHANNELS.has(rawChannel) ? rawChannel : "other";
  if (!UUID.test(deal) || !UUID.test(offerId)) return plain("invalid link");

  const [{data: candidate}, {data: offer, error}] = await Promise.all([
    sb.from("deal_candidates").select("id").eq("id", deal).maybeSingle(),
    sb.from("offers")
      .select("id,merchant_id,affiliate_url,product_url")
      .eq("id", offerId)
      .maybeSingle(),
  ]);
  if (!candidate || error || !offer) return plain("link not found", 404);

  const destination = String(offer.affiliate_url || offer.product_url || "");
  if (!/^https:\/\//i.test(destination)) return plain("destination unavailable", 404);

  const metadata = requestMetadata(req.headers);
  if (req.method === "GET") {
    const userAgent = (req.headers.get("user-agent") || "").slice(0, 500);
    const referer = (req.headers.get("referer") || "").slice(0, 1000);
    const {error: insertError} = await sb.from("deal_click_events").insert({
      deal_candidate_id: deal,
      offer_id: offer.id,
      merchant_id: offer.merchant_id,
      channel,
      ...metadata,
      visitor_hash: await visitorHash(req, deal, userAgent),
      user_agent: userAgent || null,
      referer: referer || null,
    });
    if (insertError) console.error("click insert", insertError);
  }

  // Known previews must not follow affiliate links and inflate merchant counters.
  if (metadata.is_bot) return plain("Fiyatzade product link preview", 200);

  return new Response(null, {
    status: 302,
    headers: {
      location: destination,
      "cache-control": "no-store",
      "referrer-policy": "no-referrer",
    },
  });
});
