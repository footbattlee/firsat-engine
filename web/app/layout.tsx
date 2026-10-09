import type { Metadata } from "next";
import "./globals.css";
import { SiteAnalytics } from "./site-analytics";
export const metadata: Metadata = {
 metadataBase: new URL("https://xn--frsatc-p9af.com"),
 title: "Fırsatcı — İyi fiyatın peşinde",
 description: "Fiyatı kontrol edilen fırsatları keşfet. Amazon, Trendyol ve Hepsiburada fiyatlarını karşılaştır, alışverişini doğrudan mağazada tamamla.",
 alternates: { canonical: "/" },
 openGraph: { title: "Fırsatcı — İyi fiyatın peşinde", description: "Güncel fiyat, açık karşılaştırma, doğrudan mağazaya bağlantı.", locale: "tr_TR", type: "website" },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
 return <html lang="tr"><body>{children}{process.env.VERCEL_ENV === "production" && <SiteAnalytics />}</body></html>;
}
