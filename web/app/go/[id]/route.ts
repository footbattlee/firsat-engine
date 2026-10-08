import { getSnapshot } from "../../../lib/deals";
import { eligible, safeDestination } from "../../../lib/policy";
export const dynamic = "force-dynamic";
export async function GET(_req: Request, context: { params: Promise<{ id: string }> }) {
 const { id } = await context.params;
 try {
  const row = await getSnapshot(id);
  if (!row || !eligible(row)) return new Response(
   '<!doctype html><html lang="tr"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fırsat güncelleniyor | Fırsatcı</title><body style="font:18px system-ui;max-width:560px;margin:15vh auto;padding:24px"><h1>Bu fırsatın fiyatı güncelleniyor.</h1><p>Eski bir fiyatla yönlendirmemek için bağlantıyı geçici olarak durdurduk.</p><a href="/">Güncel fırsatlara dön →</a></body></html>',
   { status: 410, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
  const destination = safeDestination(row.affiliate_url || row.product_url, row.merchant_slug);
  if (!destination) return new Response("Bağlantı kullanılamıyor", { status: 404 });
  // No stripping/rebuilding of affiliate query parameters. No storefront fetch at click time.
  return new Response(null, { status: 302, headers: { Location: destination, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex" } });
 } catch { return new Response("Fiyat kontrolü şu anda kullanılamıyor. Lütfen ana sayfadan tekrar deneyin.", { status: 503, headers: { "Cache-Control": "no-store" } }); }
}
export const HEAD = GET;
