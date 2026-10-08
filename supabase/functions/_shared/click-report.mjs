const escapeHtml = v => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
const fmt = new Intl.DateTimeFormat("tr-TR", {timeZone: "Europe/Istanbul", dateStyle: "short", timeStyle: "short"});
const ranked = (map, limit) => [...map.entries()].sort((a,b) => b[1][0]-a[1][0] || b[1][1]-a[1][1]).slice(0,limit);
export function formatClickReport(report) {
  const rows = report.rows || [];
  const total = rows.reduce((n,r) => n + Number(r.clicks || 0), 0);
  const uncertain = rows.reduce((n,r) => n + Number(r.unverified_clicks || 0), 0);
  const maps = [new Map(), new Map(), new Map()];
  for (const r of rows) {
    [r.channel || "other", r.merchant || "-", r.title || "-"].forEach((name,i) => {
      const pair = maps[i].get(name) || [0,0];
      pair[0] += Number(r.clicks || 0); pair[1] += Number(r.unverified_clicks || 0);
      maps[i].set(name, pair);
    });
  }
  const start = fmt.format(new Date(report.period_start));
  const end = fmt.format(new Date(report.period_end));
  const website = report.website;
  const lines = ["📊 <b>Fırsatcı Ziyaret ve Tıklama Raporu</b>",
    "Dönem: <b>" + start + " – " + end + "</b> (Türkiye saati; bitiş hariç)",
    ...(website ? ["", "<b>🌐 fırsatcı.com</b>",
      "Ana sayfa açılışı: <b>" + Number(website.page_views || 0) + "</b>",
      "Ana sayfadan mağazaya gidiş: <b>" + Number(website.outbound_clicks || 0) + "</b>",
      "Belirsiz mağaza isteği: " + Number(website.unverified_outbound || 0) + " (gidiş toplamına dahil değil)",
      "Ana sayfa sayacı, görünür sayfanın tarayıcı sinyalidir; yönlendirme linkleri ziyaret sayılmaz.",
      "", "<b>📱 Sosyal paylaşım bağlantıları</b>"] : []),
    "👆 Tarayıcı açılış sinyali olan: <b>" + total + "</b>",
    "❔ Belirsiz istek: <b>" + uncertain + "</b> (açılış toplamına dahil değil)",
    "🤖 Bot / ön yükleme isteği: " + Number(report.bot_requests || 0) + " (hariç)",
    "", "Kişi sayısı değildir; aynı sayfa/ürün ve kanaldaki günlük tekrarlar tek sayılır.",
    "Belirsiz istekler insan da olabilir, otomatik bağlantı kontrolü de.",
    "Amazon satırı bizim bağlantı ölçümümüzdür; Amazon Gelir Ortaklığı verisi değildir."];
  const line = ([name, [count, unknown]]) => "• " + escapeHtml(name.slice(0,120)) + ": <b>" + count + "</b> açılış" + (unknown ? " · " + unknown + " belirsiz" : "");
  if (maps[0].size) lines.push("", "<b>Kanallar</b>", ...ranked(maps[0],10).map(line));
  if (maps[1].size) lines.push("", "<b>Mağazalar</b>", ...ranked(maps[1],10).map(line));
  const products = ranked(new Map([...maps[2]].filter(([,pair]) => pair[0] > 0)),10);
  if (products.length) lines.push("", "<b>En çok açılan ürünler</b>", ...products.map(([title, pair]) => "• " + escapeHtml(title.slice(0,100)) + " — " + pair[0]));
  // Keep whole lines so Telegram HTML/entity syntax cannot be cut in half.
  const kept = []; let length = 0;
  for (const text of lines) {if (length + text.length + 1 > 4000) break; kept.push(text); length += text.length + 1;}
  return kept.join("\n");
}
