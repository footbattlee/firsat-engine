"use client";

import { Analytics, type BeforeSend } from "@vercel/analytics/next";

const beforeSend: BeforeSend = (event) => {
 const url = new URL(event.url);
 if (!["xn--frsatc-p9af.com", "www.xn--frsatc-p9af.com"].includes(url.hostname)) return null;
 // Search text and affiliate query parameters do not belong in visitor analytics.
 url.search = "";
 url.hash = "";
 return { ...event, url: url.toString() };
};

export function SiteAnalytics() {
 return <Analytics beforeSend={beforeSend} debug={false} />;
}
