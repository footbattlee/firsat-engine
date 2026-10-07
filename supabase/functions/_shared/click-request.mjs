// Fetch Metadata indicates browser navigation, not a verified person.
// Missing headers are deliberately kept as unverified, never assumed human.
const BOT_UA = /bot|crawler|spider|preview|facebookexternalhit|headlesschrome|whatsapp/i;
export function requestMetadata(headers) {
  const purpose = ["purpose", "sec-purpose", "x-purpose"].map(k => headers.get(k) || "").join(" ").trim().slice(0, 160);
  const fetchMode = (headers.get("sec-fetch-mode") || "").toLowerCase().slice(0, 40);
  const fetchDest = (headers.get("sec-fetch-dest") || "").toLowerCase().slice(0, 40);
  const fetchUser = (headers.get("sec-fetch-user") || "").slice(0, 10);
  const ua = headers.get("user-agent") || "";
  const kind = BOT_UA.test(ua) ? "bot" :
    /prefetch|prerender|preview/i.test(purpose) ? "prefetch" :
    fetchMode === "navigate" && fetchDest === "document" && fetchUser === "?1" ? "navigation" : "unverified";
  return {request_kind: kind, request_purpose: purpose || null,
    fetch_mode: fetchMode || null, fetch_dest: fetchDest || null, fetch_user: fetchUser || null,
    is_bot: kind === "bot" || kind === "prefetch"};
}
